# Shared by the scenario scripts. Source it after `cd` to the repo root.
#
# TOPOLOGY=single (default): one seller, the buyer talks to seller1 directly.
# TOPOLOGY=tf1:             three sellers behind nginx (M8), the buyer talks to lb.
TOPOLOGY=${TOPOLOGY:-single}
case $TOPOLOGY in
  single) SELLERS="seller1";                 TARGET="http://seller1:8000" ;;
  tf1)    SELLERS="seller1 seller2 seller3"; TARGET="http://lb:8080" ;;
  *) echo "unknown TOPOLOGY=$TOPOLOGY (single|tf1)" >&2; exit 2 ;;
esac

# start_sellers [VAR=value ...] -- (re)start every seller of the topology with the
# given environment, wait until healthy, and (tf1) restart nginx so it resolves
# the sellers' current addresses.
start_sellers() {
  env "$@" docker compose up -d --wait $SELLERS 2>&1 | grep -v "^ Container" || true
  if [ "$TOPOLOGY" = tf1 ]; then
    docker compose up -d --no-deps lb >/dev/null 2>&1
    docker compose restart lb >/dev/null 2>&1
    until docker compose exec -T lb wget -q -O /dev/null http://seller1:8000/health 2>/dev/null; do sleep 0.5; done
  fi
}

# restart_sellers [VAR=value ...] -- restart the seller processes (new DB sessions).
restart_sellers() {
  env "$@" docker compose restart $SELLERS >/dev/null 2>&1
  start_sellers "$@"
}
