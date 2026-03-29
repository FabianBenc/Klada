#!/bin/bash

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL="http://127.0.0.1:5000"   # Change if hosted elsewhere
USERNAME="admin"
PASSWORD="password123"
COOKIE_JAR=$(mktemp /tmp/psk_cookies.XXXXXX)

# ── Bet URLs ──────────────────────────────────────────────────────────────────
# Add one URL per line between the parentheses
TICKETS=(
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUEhXOEtHMzk3RzAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.rxSJRsUaH4GQo3hqw7OJz3kOMpYVx3Lt5T2im_TKkkA&source=SB"
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUFBEWEozUTlBMDAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.L1We5U9y6PoYRKfGMqU8CoZtCHJb6VCV55M8W7XkuIU&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUFBEWEozUTlBMDAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.L1We5U9y6PoYRKfGMqU8CoZtCHJb6VCV55M8W7XkuIU%26source%3DSB"
    # "https://applink.psk.hr/ticketdetail?id=YET_ANOTHER_JWT..."
)

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

cleanup() { rm -f "$COOKIE_JAR"; }
trap cleanup EXIT

# ── Login ─────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}Logging in as '${USERNAME}'...${NC}"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -c "$COOKIE_JAR" \
    -X POST "${BASE_URL}/login" \
    -d "username=${USERNAME}&password=${PASSWORD}" \
    --max-redirs 5)



# Verify we actually got a session cookie
if ! grep -q "session" "$COOKIE_JAR" 2>/dev/null; then
    echo -e "${RED}Login failed — no session cookie received.${NC}"
    exit 1
fi

echo -e "${GREEN}Login successful.${NC}\n"

# ── Submit tickets ────────────────────────────────────────────────────────────
TOTAL=${#TICKETS[@]}
SUCCESS=0
FAIL=0

for i in "${!TICKETS[@]}"; do
    URL="${TICKETS[$i]}"
    NUM=$((i + 1))

    echo -e "${YELLOW}[${NUM}/${TOTAL}]${NC} Submitting: ${URL:0:80}..."

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -b "$COOKIE_JAR" \
        -c "$COOKIE_JAR" \
        -X POST "${BASE_URL}/" \
        -d "ticket_number=${URL}")

    if [[ "$HTTP_CODE" == "302" ]]; then
        echo -e "  ${GREEN}✓ Added (HTTP ${HTTP_CODE})${NC}"
        SUCCESS=$((SUCCESS + 1))
    else
        echo -e "  ${RED}✗ Failed (HTTP ${HTTP_CODE})${NC}"
        FAIL=$((FAIL + 1))
    fi

done

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "────────────────────────────────────"
echo -e "Done. ${GREEN}${SUCCESS} added${NC} / ${RED}${FAIL} failed${NC} out of ${TOTAL} tickets."