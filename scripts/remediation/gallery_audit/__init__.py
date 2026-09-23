"""The gallery audit of the 2026-09 remediation (design: output/remediation/logs/
design_texts_images_2026-09-22.json, entry 7).

``persist_verdicts``  G0: the shorts pipeline's existing verdicts -> ``image_kind`` (applied).
``liveness``          S1: which referenced Commons files are still live, deleted or moved.
``vision``            S6: the frozen vision prompts, the transport and the verdict ledger.
``worklist``          S6/S8: the current tiers and the jobs of every G stage.
``labels``            S7: the three label sets calibration is measured against.
``calibrate``         S7: the sealed thresholds and the admission of each trigger.
``decide``            S9: the sealed rule table that turns verdicts into planned rows.

Nothing in this package writes to a database. Every production write goes through a separate,
journalled chunk writer.
"""
