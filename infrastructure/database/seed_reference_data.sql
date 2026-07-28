INSERT INTO regions (name, description)
VALUES
  ('东亚', 'East Asia'),
  ('中东', 'Middle East'),
  ('中亚', 'Central Asia'),
  ('西欧', 'Western Europe'),
  ('南亚', 'South Asia'),
  ('东欧', 'Eastern Europe')
ON CONFLICT (name) DO NOTHING;

INSERT INTO categories (name, description)
VALUES
  ('政治', 'Political events and institutional changes'),
  ('战争', 'Wars, battles, rebellions, and military conflicts'),
  ('王朝更替', 'Dynastic change and regime transition'),
  ('宗教', 'Religious emergence, spread, reform, or conflict'),
  ('经济', 'Economic and fiscal events'),
  ('贸易', 'Trade, routes, markets, and exchange networks'),
  ('科技', 'Technology, science, and invention'),
  ('文化', 'Culture, art, education, and intellectual history'),
  ('制度', 'Administrative, legal, and institutional reforms'),
  ('灾害', 'Natural disasters and epidemics')
ON CONFLICT (name) DO NOTHING;

INSERT INTO modern_countries (name, iso_code, region_id)
SELECT '中国', 'CN', id FROM regions WHERE name = '东亚'
ON CONFLICT (name) DO NOTHING;

INSERT INTO modern_countries (name, iso_code, region_id)
SELECT '日本', 'JP', id FROM regions WHERE name = '东亚'
ON CONFLICT (name) DO NOTHING;

INSERT INTO modern_countries (name, iso_code, region_id)
SELECT '伊拉克', 'IQ', id FROM regions WHERE name = '中东'
ON CONFLICT (name) DO NOTHING;

INSERT INTO modern_countries (name, iso_code, region_id)
SELECT '沙特阿拉伯', 'SA', id FROM regions WHERE name = '中东'
ON CONFLICT (name) DO NOTHING;

INSERT INTO modern_countries (name, iso_code, region_id)
SELECT '哈萨克斯坦', 'KZ', id FROM regions WHERE name = '中亚'
ON CONFLICT (name) DO NOTHING;

INSERT INTO polities (name, polity_type, region_id, start_year, end_year, description)
SELECT '隋朝', 'dynasty', id, 581, 618, 'Chinese dynasty before Tang'
FROM regions WHERE name = '东亚'
ON CONFLICT (name, start_year, end_year) DO NOTHING;

INSERT INTO polities (name, polity_type, region_id, start_year, end_year, description)
SELECT '唐朝', 'dynasty', id, 618, 907, 'Chinese dynasty from 618 to 907'
FROM regions WHERE name = '东亚'
ON CONFLICT (name, start_year, end_year) DO NOTHING;

INSERT INTO polities (name, polity_type, region_id, start_year, end_year, description)
SELECT '阿拔斯王朝', 'caliphate', id, 750, 1258, 'Abbasid Caliphate'
FROM regions WHERE name = '中东'
ON CONFLICT (name, start_year, end_year) DO NOTHING;

INSERT INTO polities (name, polity_type, region_id, start_year, end_year, description)
SELECT '法兰克王国', 'kingdom', id, 481, 843, 'Frankish kingdom'
FROM regions WHERE name = '西欧'
ON CONFLICT (name, start_year, end_year) DO NOTHING;

INSERT INTO polities (name, polity_type, region_id, start_year, end_year, description)
SELECT '日本飞鸟时代', 'period', id, 592, 710, 'Asuka period in Japan'
FROM regions WHERE name = '东亚'
ON CONFLICT (name, start_year, end_year) DO NOTHING;

INSERT INTO tools (name, description, risk_level, requires_confirmation, input_schema)
VALUES
  ('search_events_by_year', '按年份、地区、政权和分类检索历史事件', 'low', false, '{}'::jsonb),
  ('search_events_by_range', '按时间段检索历史事件', 'low', false, '{}'::jsonb),
  ('get_event_detail', '获取历史事件详情、来源和关系', 'low', false, '{}'::jsonb),
  ('compare_regions', '对比多个地区在某个时间范围内的历史事件', 'low', false, '{}'::jsonb),
  ('find_related_events', '查找事件之间可能存在的关联', 'low', false, '{}'::jsonb),
  ('import_events', '批量导入历史事件', 'medium', true, '{}'::jsonb),
  ('update_event', '修改历史事件记录', 'medium', true, '{}'::jsonb)
ON CONFLICT (name) DO NOTHING;

