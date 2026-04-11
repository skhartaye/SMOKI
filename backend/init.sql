-- SMOKi Database Initialization Script
-- This script creates the necessary tables for the SMOKi web application

-- Create database if it doesn't exist (this line might not work in all environments)
-- CREATE DATABASE IF NOT EXISTS smoki_db;

-- Use the database
-- \c smoki_db;

-- Create sensor_data table
CREATE TABLE IF NOT EXISTS sensor_data (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    temperature DECIMAL(5,2),
    humidity DECIMAL(5,2),
    vocs DECIMAL(8,2),
    nitrogen_dioxide DECIMAL(8,4),
    carbon_monoxide DECIMAL(8,4),
    pm25 DECIMAL(8,2),
    pm10 DECIMAL(8,2),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Create violators table for detection data
CREATE TABLE IF NOT EXISTS violators (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    license_plate VARCHAR(20),
    smoke_density DECIMAL(5,2),
    smoke_color VARCHAR(50),
    confidence DECIMAL(4,3),
    image_path TEXT,
    location VARCHAR(255),
    vehicle_type VARCHAR(50),
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Create users table for authentication
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_sensor_data_timestamp ON sensor_data(timestamp);
CREATE INDEX IF NOT EXISTS idx_violators_timestamp ON violators(timestamp);
CREATE INDEX IF NOT EXISTS idx_violators_status ON violators(status);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Create a trigger to update the updated_at column
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply the trigger to violators table
DROP TRIGGER IF EXISTS update_violators_updated_at ON violators;
CREATE TRIGGER update_violators_updated_at
    BEFORE UPDATE ON violators
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Apply the trigger to users table
DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Insert sample data (optional, for testing)
-- Uncomment the following lines if you want sample data

-- INSERT INTO sensor_data (temperature, humidity, vocs, nitrogen_dioxide, carbon_monoxide, pm25, pm10) VALUES
-- (23.5, 45.2, 120.5, 0.03, 0.5, 8.2, 12.1),
-- (24.1, 47.8, 135.2, 0.04, 0.6, 9.1, 13.5),
-- (22.8, 43.1, 110.8, 0.02, 0.4, 7.5, 11.2);

-- Create a default admin user (password: admin123)
-- Note: In production, use a secure password and proper hashing
-- INSERT INTO users (username, email, password_hash, is_admin) VALUES
-- ('admin', 'admin@smoki.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj6hsxq5S/kS', TRUE);

-- Grant necessary permissions (adjust as needed for your setup)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;