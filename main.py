import time

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.message.components import At
from astrbot.core.utils.plugin_kv_store import PluginKVStoreMixin


class ContinuousChatPlugin(Star, PluginKVStoreMixin):
    """群聊连续对话插件。

    用户通过 @机器人 或唤醒词唤醒后，其后续每条消息无需再唤醒即可触发 AI，
    且每发一条消息都会刷新超时计时（滑动窗口），超时自动退出。
    """

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    # ---------- 工具方法 ----------

    @staticmethod
    def _key(group_id, user_id) -> str:
        return f"active_{group_id}_{user_id}"

    def _timeout(self) -> int:
        try:
            return max(5, int(self.config.get("timeout_seconds", 60)))
        except (TypeError, ValueError):
            return 60

    async def _is_active(self, group_id: str, user_id: str) -> bool:
        """惰性超时判断：当前时间 > 过期时间戳 则视为不活跃。"""
        expire = await self.get_kv_data(self._key(group_id, user_id), None)
        if expire is None:
            return False
        try:
            return time.time() < float(expire)
        except (TypeError, ValueError):
            return False

    async def _activate(self, group_id: str, user_id: str) -> None:
        """记录/刷新活跃状态，过期时间 = 当前时间 + timeout_seconds。"""
        expire = time.time() + self._timeout()
        await self.put_kv_data(self._key(group_id, user_id), expire)

    def _group_enabled(self, group_id: str) -> bool:
        whitelist = self.config.get("whitelist_groups") or []
        return not whitelist or str(group_id) in {str(g) for g in whitelist}

    def _at_bot(self, event: AstrMessageEvent) -> bool:
        for seg in event.get_messages():
            if isinstance(seg, At) and str(seg.qq) == str(event.get_self_id()):
                return True
        return False

    def _hit_wake_word(self, event: AstrMessageEvent) -> bool:
        words = [str(w).strip() for w in (self.config.get("wake_words") or [])]
        words = [w for w in words if w]
        if not words:
            return False
        text = (event.message_str or "").lower()
        return any(w.lower() in text for w in words)

    # ---------- 消息监听：唤醒 / 刷新 / 强制唤醒 ----------

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_group_message(self, event: AstrMessageEvent):
        group_id = event.message_obj.group_id
        user_id = event.get_sender_id()
        # 群 ID / 用户 ID 为空则跳过；机器人自己的消息不处理
        if not group_id or not user_id:
            return
        if str(user_id) == str(event.get_self_id()):
            return
        if not self._group_enabled(group_id):
            return

        gid, uid = str(group_id), str(user_id)

        if await self._is_active(gid, uid):
            # 活跃用户：每条消息都刷新过期时间（滑动窗口）
            await self._activate(gid, uid)
            logger.debug(
                f"[continuous_chat] 刷新活跃状态 群{gid} 用户{uid} "
                f"timeout={self._timeout()}s",
            )
        else:
            logger.debug(f"[continuous_chat] 用户已超时退出 群{gid} 用户{uid}")

        # 唤醒判定：@机器人 或 命中唤醒词（忽略大小写）
        at_wake = self.config.get("enable_at_wake", True) and self._at_bot(event)
        word_wake = self.config.get("enable_word_wake", True) and self._hit_wake_word(
            event,
        )
        if at_wake or word_wake:
            await self._activate(gid, uid)
            logger.info(
                f"[continuous_chat] 用户唤醒 "
                f"({'@' if at_wake else '唤醒词'}) 群{gid} 用户{uid}，"
                f"连续对话保持 {self._timeout()}s",
            )
            # 唤醒消息本身已满足 is_at_or_wake_command，直接放行
            return

        # 非唤醒消息：活跃用户强制触发 LLM，免再次唤醒
        if await self._is_active(gid, uid) and not event.is_at_or_wake_command:
            if not (event.message_str or "").lstrip().startswith("/"):
                event.is_at_or_wake_command = True
                logger.info(
                    f"[continuous_chat] 连续对话免唤醒 群{gid} 用户{uid}："
                    f"{(event.message_str or '')[:30]}",
                )

    # ---------- LLM 请求拦截 ----------

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req):
        group_id = event.message_obj.group_id
        # 私聊 / 群 ID 为空：跳过本插件逻辑，正常放行
        if not group_id:
            return
        if not self._group_enabled(group_id):
            return
        user_id = event.get_sender_id()
        if not user_id or str(user_id) == str(event.get_self_id()):
            return

        gid, uid = str(group_id), str(user_id)
        if not await self._is_active(gid, uid):
            # 不活跃：阻止本次 LLM 调用，机器人不回复
            logger.info(
                f"[continuous_chat] 拦截未唤醒用户的 LLM 请求 群{gid} 用户{uid}",
            )
            event.stop_event()
