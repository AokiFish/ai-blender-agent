#!/bin/bash
# 分段并行下载，每段追加式续传，对抗代理频繁重置连接
# 用法: segdl.sh <url> <out_final> <total_size> <nseg> <tmpdir>
URL="$1"; OUT="$2"; TOTAL="$3"; NSEG="$4"; TMP="$5"
mkdir -p "$TMP"
chunk=$(( (TOTAL + NSEG - 1) / NSEG ))

seg_task(){
  local idx=$1 start=$2 end=$3
  local sf="$TMP/seg_$idx"
  local want=$(( end - start + 1 ))
  while :; do
    local have=$(stat -c%s "$sf" 2>/dev/null || echo 0)
    [ "$have" -ge "$want" ] && { echo "seg$idx DONE"; return 0; }
    local from=$(( start + have ))
    curl -sL --ssl-no-revoke --connect-timeout 15 --max-time 600 \
      -r "$from-$end" "$URL" >> "$sf" 2>/dev/null
    sleep 1
  done
}

pids=()
for i in $(seq 0 $((NSEG-1))); do
  s=$(( i * chunk ))
  e=$(( s + chunk - 1 ))
  [ $e -ge $TOTAL ] && e=$(( TOTAL - 1 ))
  seg_task "$i" "$s" "$e" &
  pids+=($!)
done
for p in "${pids[@]}"; do wait "$p"; done

# 合并
> "$OUT"
for i in $(seq 0 $((NSEG-1))); do cat "$TMP/seg_$i" >> "$OUT"; done
final=$(stat -c%s "$OUT" 2>/dev/null || echo 0)
echo "FINAL $OUT size=$final expected=$TOTAL"
[ "$final" -eq "$TOTAL" ] && rm -rf "$TMP" && echo "ALL_OK" || echo "SIZE_MISMATCH"
