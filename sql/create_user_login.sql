-- Stores login credentials for a gym user (one login per user).
CREATE TABLE user_login (
    user_id       UUID PRIMARY KEY,
    password_hash TEXT NOT NULL,
    last_login_at TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_user_login_gym_user
        FOREIGN KEY (user_id)
        REFERENCES gym_user (user_id)
        ON DELETE CASCADE
);
