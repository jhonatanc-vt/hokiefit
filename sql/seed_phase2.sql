
BEGIN;


INSERT INTO location (location_id, name, address, capacity)
SELECT gen_random_uuid(), v.name, v.address, v.capacity
FROM (VALUES
  ('McComas Hall Weight Room',       'McComas Hall, Virginia Tech, Blacksburg, VA',        120),
  ('McComas Hall Cardio Deck',       'McComas Hall, Virginia Tech, Blacksburg, VA',         80),
  ('McComas Hall Studio A',          'McComas Hall, Virginia Tech, Blacksburg, VA',         40),
  ('McComas Hall Studio B',          'McComas Hall, Virginia Tech, Blacksburg, VA',         40),
  ('McComas Hall Basketball Courts', 'McComas Hall, Virginia Tech, Blacksburg, VA',        100),
  ('McComas Hall Climbing Wall',     'McComas Hall, Virginia Tech, Blacksburg, VA',         25),
  ('War Memorial Hall Gym',          'War Memorial Hall, Virginia Tech, Blacksburg, VA',   150),
  ('War Memorial Hall Pool',         'War Memorial Hall, Virginia Tech, Blacksburg, VA',    60),
  ('War Memorial Hall Studio',       'War Memorial Hall, Virginia Tech, Blacksburg, VA',    35),
  ('War Memorial Hall Weight Room',  'War Memorial Hall, Virginia Tech, Blacksburg, VA',    70),
  ('Rector Field House Track',       'Rector Field House, Virginia Tech, Blacksburg, VA',  200),
  ('Southgate Field Complex',        'Southgate Drive, Virginia Tech, Blacksburg, VA',     300),
  ('Outdoor Tennis Courts',          'Washington Street, Virginia Tech, Blacksburg, VA',    48),
  ('Outdoor Basketball Courts',      'Virginia Tech, Blacksburg, VA',                       40),
  ('Sand Volleyball Courts',         'Virginia Tech, Blacksburg, VA',                       36),
  ('Racquetball Courts',             'McComas Hall, Virginia Tech, Blacksburg, VA',         16),
  ('Indoor Cycling Room',            'McComas Hall, Virginia Tech, Blacksburg, VA',         30),
  ('Martial Arts Room',              'War Memorial Hall, Virginia Tech, Blacksburg, VA',    30)
) AS v(name, address, capacity)
WHERE NOT EXISTS (SELECT 1 FROM location l WHERE l.name = v.name);


INSERT INTO location_hours (location_id, day_of_week, open_time, close_time, is_closed)
SELECT l.location_id,
       d.day,
       CASE WHEN d.day = 'sun' THEN NULL ELSE TIME '06:00' END,
       CASE WHEN d.day = 'sun' THEN NULL
            WHEN d.day = 'fri' THEN TIME '20:00'
            ELSE TIME '22:00' END,
       d.day = 'sun'
FROM location l
CROSS JOIN (VALUES ('mon'),('tue'),('wed'),('thu'),('fri'),('sat'),('sun')) AS d(day)
WHERE NOT EXISTS (SELECT 1 FROM location_hours h WHERE h.location_id = l.location_id);


INSERT INTO gym_user (user_id, first_name, last_name, email, phone_number, date_joined, role)
SELECT gen_random_uuid(), v.first_name, v.last_name, v.email, v.phone, v.joined::date, 'instructor'
FROM (VALUES
  ('Jordan',  'Miles',   'jordan.miles@example.test',   '555-0201', '2026-08-25'),
  ('Kendall', 'Brooks',  'kendall.brooks@example.test', '555-0202', '2026-08-25'),
  ('Harper',  'Quinn',   'harper.quinn@example.test',   '555-0203', '2026-08-26'),
  ('Logan',   'Hayes',   'logan.hayes@example.test',    '555-0204', '2026-08-27'),
  ('Sydney',  'Torres',  'sydney.torres@example.test',  '555-0205', '2026-08-28')
) AS v(first_name, last_name, email, phone, joined)
WHERE NOT EXISTS (SELECT 1 FROM gym_user u WHERE u.email = v.email);


WITH ins AS (
  SELECT user_id, row_number() OVER (ORDER BY email) AS rn, count(*) OVER () AS n
  FROM gym_user WHERE role = 'instructor'
),
v(k, name, description, start_date) AS (VALUES
  (1,  'HIIT Bootcamp',        'High-intensity interval training circuits',     DATE '2026-09-02'),
  (2,  'Spin Class',           'Indoor cycling with music',                     DATE '2026-09-03'),
  (3,  'Pilates Core',         'Core strength and flexibility',                 DATE '2026-09-04'),
  (4,  'Powerlifting Club',    'Squat, bench and deadlift technique',           DATE '2026-09-05'),
  (5,  'Lap Swim Group',       'Coached lap swimming for all levels',           DATE '2026-09-08'),
  (6,  'Zumba',                'Dance cardio workout',                          DATE '2026-09-09'),
  (7,  'Rock Climbing Crew',   'Bouldering and top-rope sessions',              DATE '2026-09-10'),
  (8,  'Running Club',         'Group runs on the track and around campus',     DATE '2026-09-11'),
  (9,  'Pickup Basketball',    'Organized pickup games',                        DATE '2026-09-12'),
  (10, 'Intramural Soccer',    'Weekly small-sided soccer games',               DATE '2026-09-15'),
  (11, 'Tennis Clinic',        'Drills and match play',                         DATE '2026-09-16'),
  (12, 'Volleyball League',    'Sand volleyball league nights',                 DATE '2026-09-17'),
  (13, 'Boxing Fundamentals',  'Footwork, pads and conditioning',               DATE '2026-09-18'),
  (14, 'Kickboxing Cardio',    'Cardio kickboxing class',                       DATE '2026-09-19'),
  (15, 'Mobility and Stretch', 'Recovery, mobility and stretching',             DATE '2026-09-22'),
  (16, 'Barbell Basics',       'Learn the main barbell lifts safely',           DATE '2026-09-23'),
  (17, 'Racquetball Ladder',   'Ranked racquetball challenge matches',          DATE '2026-09-24'),
  (18, 'Evening Yoga',         'Slow-flow yoga to end the day',                 DATE '2026-09-25')
)
INSERT INTO gym_group (group_id, instructor_id, name, description, start_date)
SELECT gen_random_uuid(), ins.user_id, v.name, v.description, v.start_date
FROM v JOIN ins ON ins.rn = (v.k % ins.n) + 1
WHERE NOT EXISTS (SELECT 1 FROM gym_group g WHERE g.name = v.name);


WITH g AS (
  SELECT group_id, name, row_number() OVER (ORDER BY name) AS rn
  FROM gym_group gg
  WHERE NOT EXISTS (SELECT 1 FROM activity a WHERE a.group_id = gg.group_id)
),
l AS (
  SELECT location_id, row_number() OVER (ORDER BY name) AS rn, count(*) OVER () AS n
  FROM location
)
INSERT INTO activity (activity_id, group_id, location_id, name, description, start_time, end_time, capacity)
SELECT gen_random_uuid(),
       g.group_id,
       l.location_id,
       g.name || ' Session',
       'Weekly ' || lower(g.name) || ' meeting',
       TIMESTAMP '2026-11-02 08:00' + (g.rn - 1) * INTERVAL '1 day' + (g.rn % 4) * INTERVAL '3 hours',
       TIMESTAMP '2026-11-02 09:00' + (g.rn - 1) * INTERVAL '1 day' + (g.rn % 4) * INTERVAL '3 hours',
       15 + (g.rn % 4) * 5
FROM g JOIN l ON l.rn = ((g.rn - 1) % l.n) + 1;


WITH u AS (
  SELECT user_id, row_number() OVER (ORDER BY email) AS rn
  FROM gym_user WHERE role = 'gym_user'
),
g AS (
  SELECT group_id, row_number() OVER (ORDER BY name) AS rn, count(*) OVER () AS n
  FROM gym_group
)
INSERT INTO gym_group_membership (group_id, user_id, joined_date)
SELECT g.group_id, u.user_id, DATE '2026-10-01' + (u.rn % 20)::int
FROM u JOIN g ON g.rn = ((u.rn - 1) % g.n) + 1
UNION ALL
SELECT g.group_id, u.user_id, DATE '2026-10-05' + (u.rn % 20)::int
FROM u JOIN g ON g.rn = ((u.rn + 6) % g.n) + 1
ON CONFLICT DO NOTHING;


WITH u AS (
  SELECT user_id, row_number() OVER (ORDER BY email) AS rn
  FROM gym_user WHERE role = 'gym_user'
),
a AS (
  SELECT activity_id, row_number() OVER (ORDER BY name) AS rn, count(*) OVER () AS n
  FROM activity
)
INSERT INTO registration (user_id, activity_id, registration_date)
SELECT u.user_id, a.activity_id, DATE '2026-10-22' + (u.rn % 5)::int
FROM u JOIN a ON a.rn = ((u.rn - 1) % a.n) + 1
UNION ALL
SELECT u.user_id, a.activity_id, DATE '2026-10-24' + (u.rn % 5)::int
FROM u JOIN a ON a.rn = ((u.rn + 9) % a.n) + 1
ON CONFLICT DO NOTHING;


WITH u AS (
  SELECT user_id, row_number() OVER (ORDER BY email) AS rn
  FROM gym_user gu
  WHERE NOT EXISTS (SELECT 1 FROM subscription s WHERE s.user_id = gu.user_id)
)
INSERT INTO subscription (subscription_id, user_id, subscription_type, start_date, end_date, status, price)
SELECT gen_random_uuid(),
       u.user_id,
       CASE WHEN u.rn % 3 = 0 THEN 'monthly' ELSE 'student' END,
       CASE WHEN u.rn % 3 = 0 THEN DATE '2026-10-01' ELSE DATE '2026-08-20' END,
       CASE WHEN u.rn % 3 = 0 THEN DATE '2026-10-31' ELSE DATE '2027-05-15' END,
       'active',
       CASE WHEN u.rn % 3 = 0 THEN 25.00 ELSE 0.00 END
FROM u;

COMMIT;

SELECT 'gym_user' AS table_name, count(*) FROM gym_user
UNION ALL SELECT 'location', count(*) FROM location
UNION ALL SELECT 'location_hours', count(*) FROM location_hours
UNION ALL SELECT 'gym_group', count(*) FROM gym_group
UNION ALL SELECT 'gym_group_membership', count(*) FROM gym_group_membership
UNION ALL SELECT 'activity', count(*) FROM activity
UNION ALL SELECT 'registration', count(*) FROM registration
UNION ALL SELECT 'subscription', count(*) FROM subscription
UNION ALL SELECT 'session', count(*) FROM session;
