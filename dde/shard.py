"""Roda um pedaco dos mocks do teste decisivo (mocks_dde.py do GPT, sem mudar a fisica) com saida propria por shard.
Uso: python dde/shard.py --sample pantheon --truth lcdm --n 13 --seed 1234 --tag pantheon_lcdm_s00_p0"""
import argparse, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / 'RESULTADO_DDE_H0' / 'scripts'))
import mocks_dde
p = argparse.ArgumentParser()
p.add_argument('--sample', required=True); p.add_argument('--truth', required=True)
p.add_argument('--n', type=int, required=True); p.add_argument('--seed', type=int, required=True); p.add_argument('--tag', required=True)
a = p.parse_args()
out = pathlib.Path(__file__).resolve().parent / 'shards' / a.tag
out.mkdir(parents=True, exist_ok=True)
mocks_dde.OUT = out          # so a saida muda; SRC (grade.jsonl) continua no caminho original
mocks_dde.run(a.sample, a.truth, a.n, a.seed)
