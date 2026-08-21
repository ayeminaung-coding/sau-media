-- Brings the `series` table up to the model in sau/models.py, and moves the
-- one existing series off the Chinese defaults the old build created it with.
--
-- The old build stored `title_zh` and rendered `{series_zh}`; the current code
-- calls the same column `title_local` and renders `{series}`, because the
-- caption is written for the audience's language, not the source animation's.
BEGIN;

ALTER TABLE series RENAME COLUMN title_zh TO title_local;
ALTER TABLE series ADD COLUMN IF NOT EXISTS language varchar(64) NOT NULL DEFAULT 'Burmese';
ALTER TABLE series ADD COLUMN IF NOT EXISTS style_example text NOT NULL DEFAULT '';

UPDATE series SET
  title_template       = 'အပိုင်း ({part}) {series}',
  caption_template     = E'အပိုင်း ({part}) {series}\n\n{hook}\n\n{hashtags}',
  next_teaser_template = '',
  language             = 'Burmese',
  updated_at           = now()
WHERE caption_template LIKE '%{series_zh}%' OR title_template LIKE '%{series_zh}%';

COMMIT;
