"""Ancient Nerds Studio: the local paper studio and the video studio.

Runs on the owner's workstation inside a MiniMax Code session (owner decision 2026-10-03:
`mcode` replaced Claude Code). Every model judgement (writing, claim check, image check,
case file, script) is made by the model in the session - by this session or by one
`mcode exec` per task inside a check - and handed to this code as files; the code only
validates, compiles and transports. Nothing in api/ or pipeline/lyra imports this package;
`pipeline.studio.ledger_cli` runs inside the API container (stdlib + SQLAlchemy). Heavy
local-only libraries are imported inside functions.

    python -m pipeline.studio paper  {list,pull,number,check,claims-export,claims-import,
                                      images-export,images-import,bundle,publish,correct,
                                      register-video}
    python -m pipeline.studio episode {init,markers-export,markers-import,check,review,voice,
                                      capture,timeline,render,thumbnail,package,
                                      register-youtube}
    python -m pipeline.studio mcode   {claim-check,image-check,marker-check,casefile-verify,
                                      validate,probe}
    python -m pipeline.studio doctor [--fix-gpu]
"""
