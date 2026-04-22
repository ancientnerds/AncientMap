"""Hero-image selection handler.

Picks the best inline probative image to use as the paper's banner hero.
No external API calls, no AI image generation — selects from the images
already embedded by the probative-image handler.

The event name `ImageGenComplete` is preserved so the judge handler doesn't
need to re-wire, but nothing is "generated" here.
"""

import logging

from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.hero_picker import pick_hero_image
from pipeline.lyra.research_events import ImageGenComplete, PresentationChecked

logger = logging.getLogger(__name__)


class ImageGenerationHandler(BaseHandler):
    def register(self):
        self.bus.on(PresentationChecked, self._on_presentation_checked)

    async def _on_presentation_checked(self, event: PresentationChecked):
        if not self.state.paper_text:
            await self.bus.emit(ImageGenComplete())
            return

        self.emit_sse({"type": "pipeline", "stage": "image_generation", "status": "start"})

        hero = pick_hero_image(
            self.state.paper_title or "",
            self.state.probative_images or [],
        )

        if hero:
            self.state.hero_image = hero
            self.emit_sse(
                {
                    "type": "status",
                    "content": f"Hero banner selected: {hero.get('title', 'Untitled')}",
                }
            )
            logger.info("[hero] set hero image for paper: %s", hero.get("src"))
        else:
            self.emit_sse(
                {
                    "type": "status",
                    "content": "No probative images available; paper ships without a banner.",
                }
            )

        self.emit_sse({"type": "pipeline", "stage": "image_generation", "status": "done"})
        await self.bus.emit(ImageGenComplete())
