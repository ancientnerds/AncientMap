// Wave 7: execute the measuring lens's corrections. One writer, doc+data trees only.
// No backticks anywhere in the template literals below (a backtick inside one terminates it).
const SHARED = 'REPO is C:/PythonProjects/AncientMap, branch main, use ./.venv/Scripts/python.exe (never bare python). ' +
'Read output/remediation/AUDIT_LOG.md, section "Wave 5 complete - the measuring lens refutes two of my own decisions", FIRST. ' +
'It lists every correction with the measurement behind it. The full report is ' +
'C:/Users/marti/.pi/agent/sessions/--C--PythonProjects-AncientMap--/subagent-artifacts/037d423f-f09b-48b2-93ae-35fff96a5093_gegenpruefer_output.md ' +
'- READ IT IN FULL, it contains the exact figures, the commands and the raw output. ' +
'HARD RULES. (1) AMEND, NEVER SILENTLY OVERWRITE. Every corrected number keeps its old value visible as a dated ' +
're-adjudication note, because these documents are the evidence record; a reader must be able to see what was claimed, ' +
'what was measured, and which one won. (2) Fix at the root: where a number came from the wrong reference point, say which ' +
'reference point is correct and why, not just the new number. (3) Do not invent any value: if you cannot re-measure a ' +
'disputed number yourself, say UNVERIFIED and leave it. (4) No database writes, no git commit, no push, no deploy. ' +
'(5) Run the project gate at the end and report its real output: ./.venv/Scripts/python.exe -m pytest -q -rs --timeout 90 ' +
'-m "not integration and not live_llm". Also run ruff format --check and ruff check on any .py file you touch - and if you ' +
'touch no .py file, say so. (6) You own ONLY these trees: output/remediation/phase3_pilot/ (PILOT.md, PILOT.jsonl, COST.md, ' +
'BRIEF_GAPS.md) and output/remediation/phase3_worklist/ (FINDER_BRIEF.md, REVIEWER_BRIEF.md, BATCH_PLAN.md). ' +
'Do NOT touch scripts/remediation/mechanical/, scripts/remediation/gallery_audit/, tests/remediation/test_mechanical.py, ' +
'tests/remediation/test_gallery_audit.py, migrations/, .github/ or scripts/remediation/vlm_pilot/ - live lanes own them. ' +
'Do NOT touch the evidence/ subdirectory files themselves: they are the raw record. ' +
'(7) Deliverable: the amended documents plus a report of every correction with file:line before and after, the measurement ' +
'that justifies it, and anything you could not verify. ';

const W7 = 'You are WAVE-7, correcting the Phase-3 pilot and worklist documents against the measuring lens. ' +
'Each item below is already adjudicated by me; execute it exactly, do not re-litigate it. ' +
'[1] PILOT.jsonl line 3, the single UNVERIFIABLE row, plus PILOT.md lines 163-165. The evidence line quotes ' +
'"node ... at 42.39647,42.58902" as if it were the named Satsurblia cave node. It is not: the node carrying that name ' +
'is at 42.3886354,42.6060480 (1.331 km from the stored point), while the quoted coordinate is an untagged self-closing ' +
'node belonging to a highway=unclassified way - and it lies OUTSIDE the fetched bounding box (the file states ' +
'maxlat=42.395, the quoted node is at lat 42.3964749), so it was never in the candidate set. The published 2.35 km is ' +
'exactly the distance to that road node. Therefore the row changes from UNVERIFIABLE to WRONG - the same shape as the ' +
'Karpasia row the pilot itself called WRONG at 3.5 km. Do this as an explicit re-adjudication: keep the original verdict ' +
'and reason visible, add the new verdict with the measurement and the date, and correct the distance list in PILOT.md:165 ' +
'from "1.28 km, 1.25 km and 2.35 km" to 1.28 / 1.25 / 1.33. Then update EVERY headline that depended on it: the batch ' +
'counts become CORRECT 28, WRONG 10, UNVERIFIABLE 0/2 as appropriate - count the rows yourself after the edit and state ' +
'the new totals in the report - and the false-negative rate becomes 25/40 = 62.5 percent, not 24/40 = 60 percent. ' +
'Recompute any confidence interval that depended on 24/40 and say what it becomes. ' +
'[2] The 285 coords-only sites. Two documents claim they can never produce a write and can be excluded from Phase 3. ' +
'That is unbacked: both cited rules speak only about coordinate findings, and the pilot proved prose and other-field ' +
'findings exist. Narrow the claim to what is supported - no CENSUS FINDING of those 285 is writable - and INCLUDE them ' +
'in Phase 3, because the pilot found three defects the census never named, two of them prose. So the Phase-3 scope is ' +
'1,813 sites, not 1,528. Update every affected figure in BATCH_PLAN.md (sites per agent, batch arithmetic, token budget, ' +
'wall clock, cost, the order table) and in both briefs, keeping the superseded 1,528 figures visible and marked as ' +
'superseded with the reason, exactly as the previous amendment did. ' +
'[3] PILOT.md 281 and 420, PILOT.jsonl 19, BRIEF_GAPS.md 104: "nearest Danube geometry 82.7 km" is the bounding-box ' +
'centre, not the geometry. With out geom the true nearest is 74.18 km (same way 434028188). The finding (the point is ' +
'not on the limes line) survives; the number is wrong by 8.5 km and is marked measured in three documents. ' +
'[4] PILOT.md 420-421: the claim that the 420 km frontier is invisible to T02 "because T02 only asks about the country" ' +
'is refuted by the pilot own citation - output/remediation/run_t02/findings.jsonl line 31 says explicitly that either ' +
'country or the coordinates are wrong and that T02 cannot tell which. The defect is real and unnamed; fix the REASON. ' +
'[5] COST.md 58-59 and 152: there is no Satsurblia named-feature query. Both 287-byte responses are Petroglyph queries ' +
'(Petroglyph/overpass and Petroglyph/overpass_bbox); no Satsurblia/overpass line exists in fetch_log.jsonl. The ' +
'conclusion (a name filter is cheaper than the raw dump) stands; the evidence for it must be corrected to what the log ' +
'actually shows. ' +
'[6] PILOT.md 339 and PILOT.jsonl 32: the 102 km distance is not derivable from the cited evidence - Q1743884 was fetched ' +
'with props=labels|descriptions only, so its coordinate is in none of the 76 evidence files, which contradicts the ' +
'traceability claim in PILOT.md section 7. The number itself is right (P625 gives 101.06 km). Either cite the provenance ' +
'honestly as measured separately outside the capture, or mark it UNVERIFIED - decide and say which. ' +
'[7] COST.md 45: "the six largest pages are 70 % of all fetched bytes" only reproduces by mixing definitions ' +
'(all/all = 65.1 %, only-200/only-200 = 69.1 %); 70 % needs the 404 travelguide page in the numerator but not the ' +
'denominator. Fix it to a figure that reproduces under one stated definition. ' +
'[8] COST.md 89 and 96 and BATCH_PLAN.md 56: "3,653,051 / 180 = 20,293" is wrong; it is 20,294.7, so 20,295. The effect ' +
'is 0.01 percent and no conclusion depends on it, but it is written as a division, so fix the arithmetic or replace it ' +
'with a value that divides exactly, and say which you chose. ' +
'[9] PILOT.md 371: "73 m from the polygon centre" - the cited centroid (41.415504, 46.219961) is 254 m away; 73 m is the ' +
'bounding-box centre (41.414438, 46.222002). The bbox values and the "inside" verdict reproduce exactly. Name the correct ' +
'reference point. ' +
'[10] Add the rule this class earned, to both Phase-3 briefs, in one or two sentences: whenever a distance is published, ' +
'name the reference point (nearest geometry, centroid, or bounding-box centre), and never label a value measured when ' +
'what was measured was a bounding box. ' +
'[11] Re-read your own edits at the end as a stranger: check that no other sentence in any document you touched still ' +
'asserts a corrected number, a corrected count, or the 1,528 scope. Grep for every old figure (82.7, 2.35, 1,528, ' +
'20,293, 70 %, 102 km, 73 m) and report each remaining hit and whether it is a legitimate historical note or a miss. ' +
'Write your report to the path given in the task.';

return await runs.run('wave7', {
  agent: 'worker',
  task: SHARED + W7,
  output: 'output/remediation/wave7/WAVE7_REPORT.md',
  context: 'fresh',
});
