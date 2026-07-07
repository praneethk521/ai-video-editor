import { FileVideo, LockKeyhole, ShieldCheck, Workflow } from "lucide-react";

const states = [
  { label: "Private media", value: "Google Drive OAuth", icon: LockKeyhole },
  { label: "Workflow", value: "Self-hosted n8n", icon: Workflow },
  { label: "Render targets", value: "16:9 and 9:16", icon: FileVideo },
  { label: "Security", value: "Manual upload only", icon: ShieldCheck }
];

export default function Page() {
  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">AI Video Editor</div>
        <nav>
          <a className="active">Projects</a>
          <a>Media</a>
          <a>Plans</a>
          <a>Renders</a>
          <a>Audit</a>
        </nav>
      </aside>
      <section className="workspace">
        <header className="topbar">
          <div>
            <h1>Projects</h1>
            <p>Private edit automation from Drive folder to manual upload package.</p>
          </div>
          <button>New project</button>
        </header>
        <section className="statusGrid">
          {states.map((item) => (
            <article className="statusCard" key={item.label}>
              <item.icon size={20} />
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </article>
          ))}
        </section>
        <section className="projectTable">
          <div className="tableHeader">
            <span>Project</span>
            <span>Status</span>
            <span>Outputs</span>
            <span>Last audit event</span>
          </div>
          <div className="tableRow">
            <span>Sample dummy media</span>
            <span className="pill">Planned</span>
            <span>Pending render</span>
            <span>media.ingested</span>
          </div>
        </section>
      </section>
    </main>
  );
}

