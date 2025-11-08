#!/bin/bash
# Script to check and compare environment variables

echo "======================================"
echo "Environment Variables Comparison"
echo "======================================"
echo ""

echo "1️⃣  PRODUCTION SERVICE (inzoneapi):"
echo "--------------------------------------"
gcloud run services describe inzoneapi \
  --region us-central1 \
  --format="value(spec.template.spec.containers[0].env)" 2>/dev/null || echo "Service not found or error"

echo ""
echo ""
echo "2️⃣  TEST SERVICE (inzoneapi-test):"
echo "--------------------------------------"
gcloud run services describe inzoneapi-test \
  --region us-central1 \
  --format="value(spec.template.spec.containers[0].env)" 2>/dev/null || echo "Service not found or error"

echo ""
echo ""
echo "3️⃣  LOCAL envs.yaml (what SHOULD be deployed to production):"
echo "--------------------------------------"
cat envs.yaml

echo ""
echo ""
echo "4️⃣  LOCAL envs.test.yaml (what SHOULD be deployed to test):"
echo "--------------------------------------"
cat envs.test.yaml

echo ""
echo "======================================"
echo "✓ Comparison complete"
echo "======================================"
