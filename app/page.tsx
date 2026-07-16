"use client";

import { useState } from "react";

type DemoControl = "mic" | "agent" | "joystick" | "dial";
type DemoTone = "white" | "blue" | "green" | "yellow" | "red";
type Surface = "app" | "cli";

type DemoEvent = {
  label: string;
  detail: string;
  tone: DemoTone;
};

const demoEvents: Record<DemoControl, DemoEvent> = {
  mic: {
    label: "Mic を押した",
    detail: "デスクトップアプリの音声入力を開始。離すと録音終了。",
    tone: "blue",
  },
  agent: {
    label: "Agent Key を選んだ",
    detail: "複数タスクのうち、選んだエージェントの画面へフォーカス。",
    tone: "green",
  },
  joystick: {
    label: "ジョイスティックを上へ",
    detail: "設定したワークフロー（例: Plan / review / debug）を起動。",
    tone: "yellow",
  },
  dial: {
    label: "ダイヤルを回した",
    detail: "推論レベルをその場で変更。深い作業と軽い作業を切り替え。",
    tone: "white",
  },
};

const appShortcuts = [
  ["コマンドメニュー", "⌘ / Ctrl + K", "⌘ / Ctrl + Shift + P も可"],
  ["新しいタスク", "⌘ / Ctrl + N", "⌘ / Ctrl + Shift + O も可"],
  ["タスクを検索", "⌘ / Ctrl + G", "過去のタスクを開く"],
  ["サイドバー", "⌘ / Ctrl + B", "表示 / 非表示"],
  ["Dictation", "Ctrl + Shift + D", "音声入力"],
  ["ターミナル", "Ctrl + `", "表示 / 非表示"],
];

const cliShortcuts = [
  ["ファイルを添付", "@", "ワークスペース内を検索"],
  ["入力履歴", "↑ / ↓", "下書きを復元"],
  ["プロンプト履歴", "Ctrl + R", "履歴を検索"],
  ["直前の出力をコピー", "Ctrl + O", "/copy と同じ"],
  ["次ターンへキュー", "Tab", "実行中に入力"],
  ["現在ターンへ指示", "Enter", "実行中に割り込み"],
];

const cliCommands = ["/plan", "/review", "/model", "/permissions", "/keymap", "/status"];

function StatusDot({ tone }: { tone: DemoTone }) {
  return <span className={`status-dot status-${tone}`} aria-hidden="true" />;
}

function ControlButton({
  active,
  control,
  label,
  onClick,
  symbol,
}: {
  active: boolean;
  control: DemoControl;
  label: string;
  onClick: (control: DemoControl) => void;
  symbol: string;
}) {
  return (
    <button
      className={`control-button control-${control}${active ? " is-active" : ""}`}
      onClick={() => onClick(control)}
      type="button"
    >
      <span className="control-symbol">{symbol}</span>
      <span>{label}</span>
    </button>
  );
}

export default function Home() {
  const [activeControl, setActiveControl] = useState<DemoControl>("agent");
  const [surface, setSurface] = useState<Surface>("app");

  const activeEvent = demoEvents[activeControl];
  const shortcuts = surface === "app" ? appShortcuts : cliShortcuts;

  const handleControl = (control: DemoControl): void => {
    setActiveControl(control);
  };

  return (
    <main>
      <nav className="topbar shell">
        <a className="brand" href="#top" aria-label="Codex Microの仕組みトップ">
          <span className="brand-mark">C<span>×</span></span>
          <span>CODEX MICRO<br /><small>MECHANISM NOTES</small></span>
        </a>
        <div className="nav-links">
          <a href="#mechanism">仕組み</a>
          <a href="#shortcuts">ショートカット</a>
          <a href="#sources">Sources</a>
        </div>
      </nav>

      <section className="hero shell" id="top">
        <div className="hero-copy">
          <p className="eyebrow"><span className="eyebrow-line" /> OPENAI × WORK LOUDER / FIELD GUIDE 01</p>
          <h1>AIへの指示を、<br /><em>手のひらから。</em></h1>
          <p className="hero-lede">
            Codex Microは「AI専用の別キーボード」ではなく、Codex / ChatGPTのタスクを物理操作へ変換するコントロールデッキ。
          </p>
          <div className="hero-actions">
            <a className="primary-button" href="#demo">仕組みを触ってみる <span>↓</span></a>
            <a className="text-button" href="#shortcuts">App / CLIのキー一覧 →</a>
          </div>
          <div className="hero-facts">
            <span><strong>13</strong> mechanical keys</span>
            <span><strong>RGB</strong> live status</span>
            <span><strong>2</strong> axis joystick</span>
          </div>
        </div>

        <div className="hero-visual" aria-label="Codex Microを抽象化したイラスト">
          <div className="orb orb-one" />
          <div className="orb orb-two" />
          <div className="device device-hero">
            <div className="device-topline"><span>kbd-1.0</span><span>WORK LOUDER INPUT</span></div>
            <div className="device-grid">
              <div className="device-dial"><span>REASON</span><b>07</b></div>
              <div className="device-agent agent-blue"><span>01</span><small>ACTIVE</small></div>
              <div className="device-agent agent-green"><span>02</span><small>DONE</small></div>
              <div className="device-agent agent-yellow"><span>03</span><small>WAIT</small></div>
              <div className="device-key key-mic">MIC</div>
              <div className="device-key key-code">CODEX</div>
              <div className="device-key key-plan">PLAN</div>
              <div className="device-key key-approve">✓</div>
              <div className="device-key key-reject">×</div>
              <div className="device-joystick"><span>↖</span></div>
            </div>
            <div className="device-bottomline"><span>USB-C / BLE</span><span>AGENT CONTROL DECK</span></div>
          </div>
          <div className="hero-caption"><StatusDot tone="green" /> 03 AGENT KEYS / LIVE</div>
        </div>
      </section>

      <section className="signal-strip">
        <div className="shell signal-inner">
          <span className="signal-kicker">THE SHORT ANSWER</span>
          <p>物理入力 <b>→</b> Work Louder Input <b>→</b> Codex / ChatGPT task <b>→</b> RGB state</p>
        </div>
      </section>

      <section className="section shell" id="mechanism">
        <div className="section-heading">
          <div><p className="eyebrow">01 / MECHANISM</p><h2>キーボードの先に、<br />タスクの状態がある。</h2></div>
          <p className="section-intro">記事から読み取れる要点を、入力・橋渡し・フィードバックの3層に分解します。重要なのは、Micro単体がAIを動かすのではなく、デスクトップ側のCodex / ChatGPTと連携している点です。</p>
        </div>
        <div className="layer-grid">
          <article className="layer-card layer-input"><span className="layer-number">01</span><span className="layer-icon">↗</span><h3>Physical input</h3><p>キー、タッチ、ジョイスティック、ロータリーエンコーダーを操作。</p><div className="layer-tag">USB-C / BLUETOOTH</div></article>
          <div className="layer-arrow">→</div>
          <article className="layer-card layer-bridge"><span className="layer-number">02</span><span className="layer-icon">◈</span><h3>Software bridge</h3><p><b>Work Louder Input</b> が入力をCodexの操作やSkillに割り当てる。</p><div className="layer-tag">MAPPING LAYER</div></article>
          <div className="layer-arrow">→</div>
          <article className="layer-card layer-agent"><span className="layer-number">03</span><span className="layer-icon">✦</span><h3>Agent workspace</h3><p>タスクの開始、承認、音声入力、モード変更などを実行。</p><div className="layer-tag">CODEX / CHATGPT</div></article>
          <div className="layer-arrow layer-arrow-down">↓</div>
          <article className="layer-card layer-feedback"><span className="layer-number">04</span><span className="layer-icon">◉</span><h3>RGB feedback</h3><p>Agent Keyの色で、待機・処理中・完了・承認待ち・エラーを返す。</p><div className="layer-tag">STATE → LIGHT</div></article>
        </div>
      </section>

      <section className="demo-section" id="demo">
        <div className="shell demo-layout">
          <div className="demo-copy">
            <p className="eyebrow">02 / INTERACTION MODEL</p>
            <h2>操作すると、<br /><em>状態が変わる。</em></h2>
            <p>4つの代表的なコントロールを押して、Microが「何を入力し、何を返すのか」を見てみましょう。</p>
            <div className="control-list">
              <ControlButton active={activeControl === "mic"} control="mic" label="Mic / push to talk" onClick={handleControl} symbol="◉" />
              <ControlButton active={activeControl === "agent"} control="agent" label="Agent / task focus" onClick={handleControl} symbol="✦" />
              <ControlButton active={activeControl === "joystick"} control="joystick" label="Joystick / workflow" onClick={handleControl} symbol="✣" />
              <ControlButton active={activeControl === "dial"} control="dial" label="Dial / reasoning" onClick={handleControl} symbol="◌" />
            </div>
          </div>
          <div className="demo-console">
            <div className="console-head"><span><i className="blink" /> LIVE LINK</span><span>CODEX WORKSPACE / 03</span></div>
            <div className="console-main">
              <div className="console-device">
                <div className="console-ring"><span>AGENT</span><b>03</b></div>
                <div className="console-keys"><span className="console-key active-key">MIC</span><span className="console-key">CMD</span><span className="console-key">✓</span><span className="console-key">×</span></div>
                <div className="console-stick">✣</div>
              </div>
              <div className="console-event"><span className="console-label">LAST INPUT</span><h3>{activeEvent.label}</h3><p>{activeEvent.detail}</p><div className="event-state"><StatusDot tone={activeEvent.tone} /><span>STATE SIGNAL</span><strong>{activeEvent.tone.toUpperCase()}</strong></div></div>
            </div>
            <div className="console-log"><span>12:40:01</span><span>input.received</span><span className="log-highlight">{activeControl}.action</span><span>→</span><StatusDot tone={activeEvent.tone} /></div>
          </div>
        </div>
      </section>

      <section className="section shell architecture-section">
        <div className="section-heading compact-heading"><div><p className="eyebrow">03 / UNDER THE HOOD</p><h2>ここまでは公式情報。<br /><em>ここからは推論。</em></h2></div><p className="section-intro">OpenAIが公開しているのは入力の割り当てと状態表示まで。内部プロトコルやグローバルホットキーの実装は公開ページでは説明されていません。下図は、公開情報から安全に言える境界を示したものです。</p></div>
        <div className="architecture-board">
          <div className="arch-row"><div className="arch-node node-user"><span>YOU</span><b>physical gesture</b><small>press / turn / flick</small></div><div className="arch-connector">→</div><div className="arch-node node-device"><span>MICRO</span><b>input event</b><small>USB-C or Bluetooth</small></div><div className="arch-connector">→</div><div className="arch-node node-software"><span>INPUT</span><b>mapping layer</b><small>Work Louder Input</small></div></div>
          <div className="arch-divider"><span>documented behavior</span><span>implementation detail / not published</span></div>
          <div className="arch-row"><div className="arch-node node-app"><span>CODEX / CHATGPT</span><b>task action</b><small>approve / plan / talk / start</small></div><div className="arch-connector arch-connector-down">↓</div><div className="arch-node node-state"><span>AGENT STATE</span><b>task status</b><small>idle / running / done / waiting / error</small></div><div className="arch-connector">→</div><div className="arch-node node-rgb"><span>RGB</span><b>feedback</b><small>light tells you what to do next</small></div></div>
        </div>
      </section>

      <section className="shortcuts-section" id="shortcuts">
        <div className="shell">
          <div className="section-heading shortcuts-heading"><div><p className="eyebrow">04 / KEYBOARD LAYER</p><h2>Codex App / CLIに、<br />ショートカットはある？</h2></div><p className="section-intro">あります。Microはそれらの操作を物理コントロールへ近づける存在です。アプリとCLIでは、同じCodexでも“キーボードの文法”が違います。</p></div>
          <div className="surface-tabs" role="tablist" aria-label="ショートカットの対象を選ぶ">
            <button className={surface === "app" ? "active" : ""} onClick={() => setSurface("app")} role="tab" aria-selected={surface === "app"} type="button"><span>DESKTOP APP</span><b>Codex / ChatGPT</b></button>
            <button className={surface === "cli" ? "active" : ""} onClick={() => setSurface("cli")} role="tab" aria-selected={surface === "cli"} type="button"><span>TERMINAL TUI</span><b>Codex CLI</b></button>
          </div>
          <div className="shortcut-table" key={surface}>
            {shortcuts.map(([action, key, note]) => <div className="shortcut-row" key={action}><span className="shortcut-action">{action}</span><kbd>{key}</kbd><span className="shortcut-note">{note}</span></div>)}
          </div>
          <div className="command-pocket"><div><span className="eyebrow">CLI BUILT-INS</span><p>スラッシュコマンドで、モデル・権限・Plan・レビューもキーボードから切り替えられます。</p></div><div className="command-list">{cliCommands.map((command) => <code key={command}>{command}</code>)}</div></div>
          <p className="customize-note"><span>⌘</span> Appは <b>Settings → Keyboard Shortcuts</b> から検索・変更。CLIは <b>/keymap</b> でTUIのキー割り当てを確認・保存できます。</p>
        </div>
      </section>

      <section className="section shell conclusion-section">
        <div className="conclusion-card"><div><p className="eyebrow">05 / THE TAKEAWAY</p><h2>Microは、<br /><em>AIのキーボード</em>ではなく<br />タスクのリモコン。</h2></div><div className="conclusion-points"><div><span>01</span><p>AIモデルへのAPIを直接叩く製品ではない</p></div><div><span>02</span><p>Codex / ChatGPTの既存操作を物理入力へ寄せる</p></div><div><span>03</span><p>タスク状態をRGBで“見る”ことで、次の判断を速くする</p></div></div></div>
        <div className="boundary-note"><span className="boundary-icon">!</span><p><b>言い切れること / 言い切れないこと</b><br />公式ページで確認できるのは、割り当て可能な操作・RGBステータス・対応OS・接続方式まで。OS全体に常駐するショートカットなのか、アプリ内イベントなのか、また設定ファイルやAPIが公開されているのかは、公開情報だけでは判断できません。</p></div>
      </section>

      <footer className="footer shell" id="sources">
        <div><p className="eyebrow">SOURCES / CHECKED 2026.07.16</p><h2>一次情報から、<br />仕組みを読む。</h2></div>
        <div className="source-list"><a href="https://openai.com/ja-JP/supply/co-lab/work-louder/" target="_blank" rel="noreferrer"><span>OFFICIAL PRODUCT</span><b>OpenAI × Work Louder / Codex Micro ↗</b></a><a href="https://learn.chatgpt.com/docs/reference/commands" target="_blank" rel="noreferrer"><span>OFFICIAL DOCS</span><b>ChatGPT desktop app commands ↗</b></a><a href="https://learn.chatgpt.com/docs/developer-commands" target="_blank" rel="noreferrer"><span>OFFICIAL DOCS</span><b>Codex CLI developer commands ↗</b></a><a href="https://www.gizmodo.jp/article/openai_codex_micro/" target="_blank" rel="noreferrer"><span>REFERENCE ARTICLE</span><b>ギズモード・ジャパンの記事 ↗</b></a></div>
        <div className="footer-bottom"><span>CODEX MICRO MECHANISM NOTES</span><span>Built as a field guide, not an OpenAI product.</span></div>
      </footer>
    </main>
  );
}
