import { Card } from "@/components/ui";
import "./dashboard.css";

export default function AppLoadingPage() {
  return <div className="dashboard" aria-busy="true" aria-label="Loading dashboard">
    <div aria-hidden="true"><div className="dash-skeleton dash-skeleton-value" /><div className="dash-skeleton dash-skeleton-label" /></div>
    <div className="dash-kpis" aria-hidden="true">{[0,1,2,3].map(index => <Card className="dash-card" key={index}><div className="dash-skeleton dash-skeleton-label" /><div className="dash-skeleton dash-skeleton-value" /><div className="dash-skeleton dash-skeleton-line" /></Card>)}</div>
    <div className="dash-action-grid" aria-hidden="true">{[0,1].map(index => <Card className="dash-card" key={index}><div className="dash-skeleton dash-skeleton-label" /><div className="dash-skeleton dash-skeleton-panel" /></Card>)}</div>
    <Card className="dash-card"><div aria-hidden="true" className="dash-skeleton dash-skeleton-panel" /></Card>
  </div>;
}
