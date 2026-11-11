import { React, html } from "../../html.js";
import { listComments, createComment } from "../../api.js";
import Spinner from "../Spinner.js";
import Banner from "../Banner.js";

// Right-rail "Reviewer Comments" tab, scoped to the selected table
// (`tableId` = that section's group key). Persisted server-side (see
// observability/comment_store.py) so notes survive a reload and are
// visible to any reviewer who later opens this run.
export default function ReviewerComments({ runId, tableId }) {
  const [comments, setComments] = React.useState(null);
  const [text, setText] = React.useState("");
  const [author, setAuthor] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState(null);

  const load = () => listComments(runId).then(setComments).catch((e) => setError(e.message));

  React.useEffect(() => { setComments(null); load(); }, [runId]);

  if (comments === null) return html`<${Spinner} label="Loading comments..." />`;

  const scoped = comments.filter((c) => c.table_id === tableId);

  const submit = async () => {
    if (!text.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await createComment(runId, { tableId, author, text });
      setText("");
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  return html`
    <div>
      ${error && html`<${Banner} kind="error">${error}<//>`}
      ${scoped.length === 0 && html`<p class="caption">No comments yet for this table.</p>`}
      ${scoped.map((c) => html`
        <div key=${c.id} class="comment">
          <div class="meta">${c.author} — ${new Date(c.created_at).toLocaleString()}</div>
          <div class="body">${c.text}</div>
        </div>
      `)}
      <div class="field">
        <label>Your name</label>
        <input type="text" value=${author} onInput=${(e) => setAuthor(e.target.value)} placeholder="Reviewer" />
      </div>
      <div class="field">
        <label>Comment</label>
        <textarea rows="3" value=${text} onInput=${(e) => setText(e.target.value)}></textarea>
      </div>
      <button class="btn" disabled=${submitting || !text.trim()} onClick=${submit}>
        ${submitting ? "Posting..." : "Add comment"}
      </button>
    </div>
  `;
}
