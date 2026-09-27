/**
 * Rendert body_html aus dem Route-Payload — das serverseitig gerenderte
 * Markdown der Pipeline (pipeline/article_html_renderer.py::markdown_to_html).
 *
 * Bewusst dangerouslySetInnerHTML statt eines zweiten Markdown-Renderers in
 * TypeScript: der Markdown-Renderer bleibt Python (react-ssr-Plan, Tasks
 * 12/13) — ein TS-Duplikat wäre genau die Doppelbeschreibung, die der Plan
 * beseitigt. markdown_to_html() jagt seine Ausgabe durch nh3.clean()
 * (Allowlist-Sanitizer), BEVOR sie ins Payload gelangt. Auf Forschungsseiten
 * setzt pipeline/research_html_renderer.inject_evidence_anchors danach nur
 * regex-geprüfte ev-NN-ids, eine regex-geprüfte YouTube-id, ganze Sekunden
 * und einen html-escapten Titel ein (Studio-Spec 2026-09-26 §2.7); eine
 * andere Quelle hat body_html nicht.
 */

export default function SanitizedMarkdownHtml({
  html,
  className,
}: {
  html: string
  className?: string
}) {
  return (
    <div
      className={className}
      dangerouslySetInnerHTML={/* nosemgrep: semgrep.tsx-dangerously-set-inner-html -- body_html is produced by pipeline/article_html_renderer.markdown_to_html, which nh3-sanitizes (allowlist) before the payload is built; on research pages pipeline/research_html_renderer.inject_evidence_anchors then adds only regex-validated ev-NN ids, the regex-validated YouTube id, integer seconds and an html-escaped title */ { __html: html }}
    />
  )
}
