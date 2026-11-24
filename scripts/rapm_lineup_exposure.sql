-- One cycle of this query runs against one pinned development season.
CREATE TEMP TABLE opportunities AS
WITH cum AS (
  SELECT game_id, stream_revision, seq, elapsed_ms,
         sum(home_delta - away_delta) OVER (
           PARTITION BY game_id, stream_revision ORDER BY seq
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
         ) AS home_margin
  FROM event
)
SELECT row_number() OVER (ORDER BY g.game_date, d.game_id, d.possession_seq) - 1 AS row_id,
       d.game_id, d.stream_revision, d.possession_seq, g.game_date, d.season_type, d.period,
       d.start_seq, d.end_seq, d.offense_team_id, d.defense_team_id,
       d.reason = 'multiple_lineups' AS multi, d.lineup_pairs, d.control_points,
       d.offense_team_id = g.home_team_id AS offense_home,
       CASE WHEN d.offense_team_id = g.home_team_id THEN 1 ELSE -1 END
         * coalesce(c.home_margin, 0) AS margin,
       greatest(coalesce(c.elapsed_ms, 0), CASE WHEN d.period <= 4 THEN 720000 * (d.period - 1)
                   ELSE 2880000 + 300000 * (d.period - 5) END) AS elapsed_from,
       e.elapsed_ms AS elapsed_to,
       CASE WHEN d.period <= 4 THEN d.period * 720000
         ELSE 2880000 + 300000 * (d.period - 4) END AS period_end
FROM possession_disposition d
JOIN game_stream gs ON gs.game_id = d.game_id AND gs.revision = d.stream_revision
JOIN game g ON g.game_id = gs.game_id AND g.revision = gs.official_game_revision
JOIN cum e ON e.game_id = d.game_id AND e.stream_revision = d.stream_revision
  AND e.seq = d.end_seq - 1
LEFT JOIN cum c ON c.game_id = d.game_id AND c.stream_revision = d.stream_revision
  AND c.seq = d.start_seq - 1
WHERE d.reason IN ('eligible', 'multiple_lineups') AND d.pilot_status = 'accepted'
  AND gs.complete AND gs.quality = 'accepted';

CREATE TEMP TABLE segments AS
SELECT p.row_id, s.stint_seq,
       list_sort(list_transform(CASE WHEN p.offense_home THEN h.player_ids ELSE a.player_ids END,
                                lambda x: cast(x AS BIGINT))) AS offense,
       list_sort(list_transform(CASE WHEN p.offense_home THEN a.player_ids ELSE h.player_ids END,
                                lambda x: cast(x AS BIGINT))) AS defense,
       least(s.end_seq, p.end_seq) - greatest(s.start_seq, p.start_seq) AS seqs,
       greatest(0, least(s.end_elapsed_ms, p.elapsed_to)
                        - greatest(s.start_elapsed_ms, p.elapsed_from)) AS ms
FROM opportunities p
JOIN stint s ON s.game_id = p.game_id AND s.stream_revision = p.stream_revision
  AND s.period = p.period AND s.start_seq < p.end_seq AND s.end_seq > p.start_seq
JOIN lineup h ON h.game_id = s.game_id AND h.stream_revision = s.stream_revision
  AND h.lineup_id = s.home_lineup_id
JOIN lineup a ON a.game_id = s.game_id AND a.stream_revision = s.stream_revision
  AND a.lineup_id = s.away_lineup_id;

CREATE TEMP TABLE cohort AS
WITH summaries AS (
  SELECT row_id, count(*) AS pieces, sum(seqs) AS covered_seqs, sum(ms) AS covered_ms,
         count(DISTINCT offense) AS offense_states, count(DISTINCT defense) AS defense_states,
         count(DISTINCT (offense, defense)) AS pairs, count_if(ms = 0) AS zero_ms_pieces,
         first(offense ORDER BY stint_seq) AS offense, first(defense ORDER BY stint_seq) AS defense
  FROM segments GROUP BY row_id
)
SELECT p.*, s.* EXCLUDE (row_id),
       CASE WHEN margin <= -10 THEN '1 down 10+'
            WHEN margin <= -3 THEN '2 down 3-9'
            WHEN margin <= 2 THEN '3 within 2'
            WHEN margin <= 9 THEN '4 up 3-9' ELSE '5 up 10+' END AS margin_band,
       least(period, 5) AS period_band,
       CASE WHEN period_end - elapsed_from <= 24000 THEN '1 0-24 s'
            WHEN period_end - elapsed_from <= 120000 THEN '2 24-120 s'
            WHEN period_end - elapsed_from <= 360000 THEN '3 120-360 s'
            ELSE '4 360+ s' END AS clock_band
FROM opportunities p JOIN summaries s USING (row_id);

CREATE TEMP VIEW pieces_with_weight AS
SELECT s.*, CASE WHEN c.covered_ms > 0 THEN ms::DOUBLE / c.covered_ms
                 ELSE 1.0 / c.pieces END AS share
FROM segments s JOIN cohort c USING (row_id);
