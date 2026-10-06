# Homelab Monitoring API

A lightweight monitoring status API for my homelab.

It collects check results from automation jobs and exposes a simple HTTP API for dashboards such as Homarr.

## Features

- FastAPI-based REST API
- SQLite storage
- Status and detail endpoints
- Automatic stale-check detection
- API-key protected status updates
- Docker image automatically built and published via GitHub Actions

## Docker

The latest image is available from GitHub Container Registry:

`ghcr.io/jack-in-the-box676/monitoring-api:latest`

## Configuration

The container uses the following environment variables:

| Variable | Description | Default |
| --- | --- | --- |
| `API_KEY` | API key required for write requests | none |
| `DB_PATH` | Path to the SQLite database | `/data/monitoring.db` |

## API

- `GET /api/status` — overview of all monitoring checks
- `GET /api/status/{check_id}` — details for a specific check
- `POST /api/status/{check_id}` — create or update a check (requires API key)

## Purpose

This is a small internal component of my homelab monitoring stack and is primarily intended for personal use.