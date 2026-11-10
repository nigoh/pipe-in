// 返事を送る手順と、書く口の形（D0079）。
// 最後に描いた図の印（段と識別子）と、書く直前に読み直した印が同じときだけ書く。違うときは書かず changed を返す。
// 選んでいる実行がボタンの条件を満たさないとき（古い画面からの知らせ）も書かない。パネルから来る値は動作と直してほしい点だけ。
import type { PipelineView } from '../domain/pipelineView.ts';
import { buildReplyText } from '../domain/replyFile.ts';
import type { ReplyText } from '../domain/replyFile.ts';
import { HERE, isRunFolderName, parseRunKey } from '../domain/runs.ts';
import type { RunKey } from '../domain/runs.ts';

export type ReplyStoreReason = 'bad_run' | 'bad_text' | 'outside' | 'exists' | 'failed';

/** 返事のファイルを書く口。実行のフォルダ名（直下は ''）と中身だけを受け取り、ファイル名は口が決める。 */
export interface ReplyStore {
  create(runId: string, text: ReplyText): Promise<{ ok: true } | { ok: false; reason: ReplyStoreReason }>;
}

/** 最後に描いた図の印 ＝ 書く直前に読み直した印の形 */
export interface ReplyOffer { key: RunKey; stage: string; id: string }
export type ReplyRefusal = 'no_offer' | 'bad_input' | 'changed' | ReplyStoreReason;

/** 図に返事の申し出があり、選んでいる実行がいまの work_dir の直下かパイプのフォルダのときだけ、申し出を作る。 */
export function replyOfferOf(view: PipelineView, selected: RunKey): ReplyOffer | null {
  const reply = view.reply ?? null;
  if (reply === null) return null;
  const parsed = parseRunKey(selected);
  if (parsed === null || parsed.place !== HERE) return null;
  if (parsed.id !== '' && !isRunFolderName(parsed.id)) return null;
  return { key: selected, stage: reply.stage, id: reply.id };
}

/**
 * 返事を書く。動作と直してほしい点だけをパネルから受け取り、段と識別子は自分が描いた図の申し出から入れる。
 * 順：申し出があるか → 中身が作れるか → 書く直前に読み直して同じか → 口で新しく作る。
 */
export async function sendReply(
  choice: { action: unknown; feedback?: unknown },
  deps: { shown: ReplyOffer | null; reread: () => Promise<ReplyOffer | null>; store: ReplyStore },
): Promise<{ ok: true } | { ok: false; reason: ReplyRefusal }> {
  const { shown } = deps;
  if (shown === null) return { ok: false, reason: 'no_offer' };
  const built = buildReplyText({ action: choice.action, stage: shown.stage, id: shown.id, feedback: choice.feedback });
  if (!built.ok) return { ok: false, reason: 'bad_input' };
  const fresh = await deps.reread();
  if (fresh === null || fresh.key !== shown.key || fresh.stage !== shown.stage || fresh.id !== shown.id) {
    return { ok: false, reason: 'changed' };
  }
  const parsed = parseRunKey(fresh.key);
  if (parsed === null) return { ok: false, reason: 'bad_run' };
  return deps.store.create(parsed.id, built.text);
}
