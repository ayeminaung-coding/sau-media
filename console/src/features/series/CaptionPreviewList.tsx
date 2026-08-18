import { Button } from "../../components/Button";
import { platformName } from "../../domain/platforms";
import type { CaptionPreview } from "../../api/types";
import { cx } from "../../lib/cx";
import "./CaptionPreviewList.css";

interface CaptionPreviewListProps {
  previews: readonly CaptionPreview[];
  onClose: () => void;
}

/**
 * What one episode publishes as, on every platform.
 *
 * Rendered by the API, by the same function the publish path calls — so this
 * is not an approximation of the caption, it is the caption.
 */
export function CaptionPreviewList({ previews, onClose }: CaptionPreviewListProps) {
  return (
    <div className="cpreview">
      <div className="cpreview__head">
        <p className="cpreview__lead faint">
          Rendered server-side by the same code that publishes, so this is exactly what goes out.
        </p>
        <Button size="sm" variant="ghost" onClick={onClose}>
          Close
        </Button>
      </div>

      <div className="cpreview__grid">
        {previews.map((preview) => {
          const near = preview.caption.length >= preview.caption_limit * 0.9;
          return (
            <article key={preview.platform} className="cpreview__card">
              <header className="cpreview__title">
                <span>{platformName(preview.platform)}</span>
                <span className={cx("cpreview__count", "mono", near && "cpreview__count--near")}>
                  {preview.caption.length}/{preview.caption_limit}
                </span>
              </header>

              {preview.title_limit > 0 ? (
                <p className="cpreview__field">
                  <span className="cpreview__label faint">Title</span>
                  {preview.title || <span className="faint">—</span>}
                </p>
              ) : (
                <p className="cpreview__field faint">No title field on this platform.</p>
              )}

              <pre className="cpreview__caption">{preview.caption}</pre>
            </article>
          );
        })}
      </div>
    </div>
  );
}
