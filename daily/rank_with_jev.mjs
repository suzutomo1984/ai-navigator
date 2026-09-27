#!/usr/bin/env node
// One ranking run; batches are serialized to stay within Jev's evaluation limits.
import fs from 'node:fs';
import { experimental_evaluate as evaluate } from 'ai';

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath) throw new Error('usage: rank_with_jev.mjs input.json output.json');
if (!process.env.AI_GATEWAY_API_KEY) throw new Error('AI_GATEWAY_API_KEY is not set');
const candidates = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
const questions = {
  on_topic: 'は、AI（生成AI・AIエージェント・AIツール）の活用や動向そのものを扱っていますか？AIが話題の中心でない記事は False です。',
  needs_coding: 'を理解・実践するのに、プログラミング、コマンド操作、API、設定ファイル編集、開発環境構築などエンジニアの知識が前提になりますか？',
  plain: 'は、特定のツール名や専門用語を知らない人でも、タイトルと要約だけで何の話か・自分に関係あるかが分かりますか？',
  actionable: 'に、読者が明日の仕事ですぐ試せる具体的な手順・考え方・チェック方法が含まれていますか？',
  is_promo: 'は、宣伝、PR、セミナー告知、アフィリエイト、または中身の薄いまとめ・ランキング記事ですか？',
};
const batches = [];
for (let i = 0; i < candidates.length; i += 15) batches.push(candidates.slice(i, i + 15));
const ranked = [];
for (const batch of batches) {
  const qs = {};
  batch.forEach((_, i) => Object.entries(questions).forEach(([key, wording]) => {
    qs[`r${i}_${key}`] = { type: 'boolean', instructions: `\`results[${i}]\` ${wording}` };
  }));
  const result = await evaluate({
    model: 'typesafe-ai/jev',
    state: { audience: '中小企業で働く40代の非エンジニア実務者', results: batch.map(a => ({ title: a.title, snippet: a.summary, source: a.source, date: a.date })) },
    questions: qs,
    maxRetries: 1,
    abortSignal: AbortSignal.timeout(120000),
  });
  batch.forEach((article, i) => {
    const score = key => {
      const value = result.answers?.[`r${i}_${key}`]?.probability;
      if (typeof value !== 'number') throw new Error(`Jev returned no ${key} probability`);
      return value;
    };
    const on_topic = score('on_topic');
    const needs_coding = score('needs_coding');
    const plain = score('plain');
    const actionable = score('actionable');
    const is_promo = score('is_promo');
    const finalScore = (0.4 * actionable + 0.25 * plain + 0.35 * (1 - needs_coding)) * (1 - 0.5 * is_promo);
    ranked.push({ ...article, on_topic, needs_coding, plain, actionable, is_promo, score: finalScore });
  });
}
ranked.sort((a, b) => b.score - a.score);
fs.writeFileSync(outputPath, JSON.stringify({ failed_batches: 0, count: ranked.length, results: ranked }, null, 2), 'utf8');
process.stdout.write(`ranked ${ranked.length} candidates\n`);
