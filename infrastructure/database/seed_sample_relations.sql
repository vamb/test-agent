WITH event_ids AS (
  SELECT title, id
  FROM historical_events
  WHERE title IN ('唐朝建立', '大化改新', '怛罗斯之战', '阿拔斯王朝建立', '安史之乱爆发')
)
INSERT INTO event_relations (
  source_event_id,
  target_event_id,
  relation_type,
  explanation,
  confidence,
  is_directional
)
SELECT
  source.id,
  target.id,
  'influence',
  '大化改新以唐朝制度为重要参照，体现唐代制度对日本律令国家建设的影响。',
  0.75,
  true
FROM event_ids source
JOIN event_ids target ON source.title = '唐朝建立' AND target.title = '大化改新'
ON CONFLICT (source_event_id, target_event_id, relation_type) DO NOTHING;

WITH event_ids AS (
  SELECT title, id
  FROM historical_events
  WHERE title IN ('怛罗斯之战', '阿拔斯王朝建立')
)
INSERT INTO event_relations (
  source_event_id,
  target_event_id,
  relation_type,
  explanation,
  confidence,
  is_directional
)
SELECT
  source.id,
  target.id,
  'conflict_link',
  '怛罗斯之战发生在唐朝与阿拔斯势力竞争中亚影响力的背景下，阿拔斯王朝建立后其东向影响增强。',
  0.70,
  false
FROM event_ids source
JOIN event_ids target ON source.title = '怛罗斯之战' AND target.title = '阿拔斯王朝建立'
ON CONFLICT (source_event_id, target_event_id, relation_type) DO NOTHING;

WITH event_ids AS (
  SELECT title, id
  FROM historical_events
  WHERE title IN ('安史之乱爆发', '怛罗斯之战')
)
INSERT INTO event_relations (
  source_event_id,
  target_event_id,
  relation_type,
  explanation,
  confidence,
  is_directional
)
SELECT
  source.id,
  target.id,
  'contemporary',
  '怛罗斯之战与安史之乱发生时间相近，均可作为 8 世纪中期唐朝内外压力变化的背景事件；该关系表示同期背景，不表示直接因果。',
  0.65,
  false
FROM event_ids source
JOIN event_ids target ON source.title = '怛罗斯之战' AND target.title = '安史之乱爆发'
ON CONFLICT (source_event_id, target_event_id, relation_type) DO NOTHING;

