CREATE TABLE IF NOT EXISTS trips (
    trip_id UUID PRIMARY KEY,
    user_id TEXT,
    origin TEXT,
    destination TEXT,
    start_date DATE,
    end_date DATE,
    travelers INTEGER DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'RUNNING',
    current_step TEXT,
    itinerary JSONB,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);