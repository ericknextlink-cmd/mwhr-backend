#!/bin/bash
# Local Docker build test script
# This simulates the production build process

set -e

echo "🔨 Testing Docker build locally..."
echo ""

# Build the Docker image
echo "Building Docker image..."
docker build -t mwhr-backend-test .

echo ""
echo "✅ Build successful!"
echo ""
echo "Testing import..."
docker run --rm mwhr-backend-test python -c "
import sys
sys.path.insert(0, '/app')
try:
    from app.api.v1.endpoints import analysis
    print('✅ SUCCESS: analysis module imported')
    print('Router:', analysis.router)
except Exception as e:
    print('❌ FAILED:', type(e).__name__, str(e))
    import traceback
    traceback.print_exc()
    sys.exit(1)
"

echo ""
echo "✅ All tests passed! Ready for deployment."
