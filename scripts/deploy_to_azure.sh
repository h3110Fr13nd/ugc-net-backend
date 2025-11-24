#!/bin/bash

# Configuration
VM_USER="azureuser"
VM_HOST="20.244.35.24"
KEY_PATH="/home/h3110fr13nd/Downloads/SECURE/Credentials/ugc-net_key (1).pem"
REMOTE_DIR="/home/azureuser/ugc-net-backend"
LOCAL_DB_CONTAINER="backend-db-1"
DB_NAME="ugc"
DB_USER="postgres"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%H:%M:%S')] $1${NC}"
    exit 1
}

# Parse arguments
MIGRATE_DB=false
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --migrate-db) MIGRATE_DB=true ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

# 1. Prerequisites Check
log "Checking prerequisites..."
command -v ssh >/dev/null 2>&1 || error "ssh is required but not installed."
command -v rsync >/dev/null 2>&1 || error "rsync is required but not installed."
command -v docker >/dev/null 2>&1 || error "docker is required but not installed."

if [ ! -f "$KEY_PATH" ]; then
    error "SSH key not found at $KEY_PATH"
fi

chmod 400 "$KEY_PATH"

# 2. VM Setup (Install Docker if missing)
log "Checking/Installing Docker on VM..."
ssh -i "$KEY_PATH" -o StrictHostKeyChecking=no "$VM_USER@$VM_HOST" << EOF
    if ! command -v docker &> /dev/null; then
        echo "Docker not found. Installing..."
        curl -fsSL https://get.docker.com -o get-docker.sh
        sudo sh get-docker.sh
        sudo usermod -aG docker $VM_USER
        echo "Docker installed. Please re-run the script to pick up group changes if this fails."
    else
        echo "Docker is already installed."
    fi
    
    if ! docker compose version &> /dev/null; then
         echo "Docker Compose plugin not found. Installing..."
         sudo apt-get update
         sudo apt-get install -y docker-compose-plugin
    fi
EOF

# 3. Code Sync
log "Syncing code to $VM_HOST..."
# Ensure remote directory exists
ssh -i "$KEY_PATH" "$VM_USER@$VM_HOST" "mkdir -p $REMOTE_DIR"

# Sync files
rsync -avz -e "ssh -i '$KEY_PATH'" \
    --exclude '.git' \
    --exclude '.venv' \
    --exclude '__pycache__' \
    --exclude 'logs' \
    --exclude 'uploads' \
    --exclude 'pgdata' \
    --exclude 'pgadmin-data' \
    --exclude 'grafana-data' \
    ./ "$VM_USER@$VM_HOST:$REMOTE_DIR"

# 4. Environment Setup
log "Setting up environment variables..."
if [ -f ".env.local" ]; then
    scp -i "$KEY_PATH" .env.local "$VM_USER@$VM_HOST:$REMOTE_DIR/.env"
else
    warn ".env.local not found! Skipping environment file copy."
fi

# 5. Database Migration (Optional)
if [ "$MIGRATE_DB" = true ]; then
    log "Starting Database Migration..."
    
    # Dump local DB
    log "Dumping local database..."
    docker exec "$LOCAL_DB_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" > dump.sql
    
    if [ $? -ne 0 ]; then
        rm dump.sql
        error "Failed to dump local database."
    fi
    
    # Transfer dump
    log "Transferring dump to VM..."
    scp -i "$KEY_PATH" dump.sql "$VM_USER@$VM_HOST:$REMOTE_DIR/dump.sql"
    rm dump.sql # Clean up local dump
    
    # Restore on VM (safe restore: backup remote DB, stop web, drop/create DB and restore)
    log "Restoring database on VM..."
    ssh -i "$KEY_PATH" "$VM_USER@$VM_HOST" << EOF
        set -e
        cd $REMOTE_DIR
        # Ensure db container is running
        docker compose up -d db
        echo "Waiting for database to be ready..."
        sleep 10

        # Backup current remote DB before touching it
        echo "Creating remote DB backup..."
        docker compose exec -T db bash -lc 'pg_dump -U $DB_USER $DB_NAME > /tmp/backup_before_restore.sql'
        docker compose cp db:/tmp/backup_before_restore.sql $REMOTE_DIR/backup_before_restore.sql || true

        # Stop web to prevent writes during restore
        echo "Stopping web service..."
        docker compose stop web || true

        # Drop and recreate the target DB to ensure a clean restore
        echo "Dropping and recreating $DB_NAME database..."
        docker compose exec -T db bash -lc "psql -U $DB_USER -d postgres -c 'DROP DATABASE IF EXISTS $DB_NAME'"
        docker compose exec -T db bash -lc "psql -U $DB_USER -d postgres -c 'CREATE DATABASE $DB_NAME'"

        # Copy dump into container and restore into empty DB
        echo "Copying dump to container and restoring..."
        docker compose cp dump.sql db:/tmp/dump.sql
        docker compose exec -T db bash -lc 'set -o pipefail; psql -U $DB_USER -d $DB_NAME -f /tmp/dump.sql'

        # Run Alembic migrations after restore to apply any latest updates
        echo "Running alembic upgrade head (if needed)"
        docker compose up -d web
        sleep 5
        docker compose exec -T web alembic upgrade head || true

        # Cleanup temporary files
        rm -f dump.sql
EOF
else
    log "Skipping database migration (use --migrate-db to enable)."
fi

# 6. Service Start
log "Starting services (web, db)..."
ssh -i "$KEY_PATH" "$VM_USER@$VM_HOST" << EOF
    cd $REMOTE_DIR
    docker compose down # Stop existing to ensure clean state or just up -d --build
    docker compose up -d --build web db
    docker compose ps
EOF

log "Deployment complete! 🚀"
