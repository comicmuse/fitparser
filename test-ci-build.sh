#!/bin/bash
# Test the CI build process locally before pushing to GitHub

set -e  # Exit on any error

echo "🧪 Testing CI build process locally..."
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

IMAGE_NAME="runcoach-ci-test"
CONTAINER_NAME="runcoach-ci-test"

# Check if we need sudo for Docker
DOCKER_CMD="docker"
if ! docker ps >/dev/null 2>&1; then
    if sudo docker ps >/dev/null 2>&1; then
        DOCKER_CMD="sudo docker"
        echo "ℹ️  Using sudo for Docker commands (user not in docker group)"
        echo ""
    else
        echo -e "${RED}✗ Docker is not accessible. Please install Docker or add user to docker group.${NC}"
        exit 1
    fi
fi

# Clean up any existing test containers
echo "🧹 Cleaning up any existing test containers..."
$DOCKER_CMD stop $CONTAINER_NAME 2>/dev/null || true
$DOCKER_CMD rm $CONTAINER_NAME 2>/dev/null || true
$DOCKER_CMD rmi $IMAGE_NAME 2>/dev/null || true

# Build the Docker image (like CI does)
echo ""
echo "🐳 Building Docker image (without strydcmd, like CI)..."
$DOCKER_CMD build -t $IMAGE_NAME .

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Docker build successful${NC}"
else
    echo -e "${RED}✗ Docker build failed${NC}"
    exit 1
fi

# Start the container (like CI does)
echo ""
echo "🚀 Starting container for health check..."
$DOCKER_CMD run -d \
    --name $CONTAINER_NAME \
    -p 5000:5000 \
    -e SECRET_KEY="ci-test-secret-key-not-for-production" \
    -e DATA_DIR=/tmp/data \
    -e OPENAI_API_KEY="sk-fake-key-for-ci" \
    -e FLASK_PORT=5000 \
    $IMAGE_NAME

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Container started${NC}"
else
    echo -e "${RED}✗ Container failed to start${NC}"
    exit 1
fi

# Wait for Flask to start
echo ""
echo "⏳ Waiting for Flask server to start..."
timeout 60 bash -c "until $DOCKER_CMD logs runcoach-ci-test 2>&1 | grep -q 'Running on'; do sleep 2; done"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Flask server started${NC}"
else
    echo -e "${RED}✗ Flask server failed to start${NC}"
    echo ""
    echo "Container logs:"
    $DOCKER_CMD logs $CONTAINER_NAME
    $DOCKER_CMD stop $CONTAINER_NAME
    $DOCKER_CMD rm $CONTAINER_NAME
    exit 1
fi

# Health check
echo ""
echo "🏥 Running health check on /status endpoint..."
sleep 3  # Give it a moment to be fully ready

for i in {1..10}; do
    if curl -f -s http://localhost:5000/status > /dev/null; then
        echo -e "${GREEN}✓ Health check passed!${NC}"
        echo ""
        echo "Response:"
        curl -s http://localhost:5000/status | python3 -m json.tool
        HEALTH_OK=1
        break
    fi
    echo "Attempt $i failed, retrying..."
    sleep 3
done

if [ -z "$HEALTH_OK" ]; then
    echo -e "${RED}✗ Health check failed after 10 attempts${NC}"
    echo ""
    echo "Container logs:"
    $DOCKER_CMD logs $CONTAINER_NAME
    $DOCKER_CMD stop $CONTAINER_NAME
    $DOCKER_CMD rm $CONTAINER_NAME
    exit 1
fi

# Clean up
echo ""
echo "🧹 Cleaning up test container..."
$DOCKER_CMD stop $CONTAINER_NAME
$DOCKER_CMD rm $CONTAINER_NAME

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ All checks passed! CI build process works correctly.${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "You can now safely push to GitHub and the CI will succeed."
echo ""
echo "Next steps:"
echo "  git add .github/ .dockerignore Dockerfile README.md"
echo "  git commit -m 'Add GitHub Actions CI/CD pipeline'"
echo "  git push origin main"
echo ""
echo "Then watch it run: https://github.com/comicmuse/fitparser/actions"
