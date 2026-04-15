"""Cover image generation handler --- generates a title image after presentation check."""

import logging

from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.research_events import ImageGenComplete, PresentationChecked

logger = logging.getLogger(__name__)


class ImageGenerationHandler(BaseHandler):
    def register(self):
        self.bus.on(PresentationChecked, self._on_presentation_checked)

    async def _on_presentation_checked(self, event: PresentationChecked):
        from pipeline.lyra.theo_images import generate_cover_image, insert_cover_image

        if not self.state.paper_text:
            await self.bus.emit(ImageGenComplete())
            return

        self.emit_sse({"type": "pipeline", "stage": "image_generation", "status": "start"})

        cover_url = await generate_cover_image(
            self.state.request_id or "unknown",
            self.state.paper_text,
            lambda e: self.emit_sse(e),
        )

        if cover_url:
            self.state.paper_text = insert_cover_image(self.state.paper_text, cover_url)

        self.emit_sse({"type": "pipeline", "stage": "image_generation", "status": "done"})
        await self.bus.emit(ImageGenComplete())
