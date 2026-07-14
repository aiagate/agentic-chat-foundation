"""LINE delivery adapter for one request-local conversation flow."""

from __future__ import annotations

from linebot.v3.messaging import AsyncMessagingApi, PushMessageRequest, TextMessage

from app.contracts.messages.conversation import ConversationResult, DeliveryResult
from app.contracts.ports.conversation import ConversationResultSender


class LineConversationResultSender(ConversationResultSender):
    """Push generated text to the originating LINE user or group."""

    def __init__(self, api: AsyncMessagingApi, destination: str) -> None:
        self._api = api
        self._destination = destination

    async def send(self, result: ConversationResult) -> DeliveryResult:
        contents = list(result.contents)
        if not contents and result.unavailable:
            contents = [result.failure_reason or "応答を作成できませんでした。"]
        if not contents:
            return DeliveryResult(
                message_id=result.message_id,
                delivered=False,
                failure_reason="Response has no text content",
            )
        try:
            for content in contents:
                await self._api.push_message(
                    PushMessageRequest(
                        to=self._destination,
                        messages=[
                            TextMessage(
                                text=content,
                                quickReply=None,
                                quoteToken=None,
                            )
                        ],
                        notificationDisabled=False,
                        customAggregationUnits=None,
                    )
                )
        except Exception as exc:
            return DeliveryResult(
                message_id=result.message_id,
                delivered=False,
                failure_reason=str(exc),
            )
        return DeliveryResult(message_id=result.message_id, delivered=True)
