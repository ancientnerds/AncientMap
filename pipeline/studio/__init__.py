"""Ancient Nerds Studio: the local paper studio and the video studio.

Runs on the owner's workstation inside a Claude Code session. Every model judgement
(writing, fact check, image check, case file, script) is made by Claude in the session and
handed to this code as files; the code only validates, compiles and transports. Nothing in
api/ or pipeline/lyra imports this package; `pipeline.studio.ledger_cli` runs inside the API
container (stdlib + SQLAlchemy). Heavy local-only libraries are imported inside functions.

    python -m pipeline.studio paper  {list,pull,number,check,claims-export,claims-import,
                                      images-export,images-import,bundle,publish,correct,
                                      register-video}
    python -m pipeline.studio episode {init,markers-export,markers-import,check,review,voice,
                                      capture,timeline,render,thumbnail,package,
                                      register-youtube}
    python -m pipeline.studio doctor [--fix-gpu]
"""
