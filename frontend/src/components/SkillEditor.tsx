"use client";

import { Plus, Trash2 } from "lucide-react";
import { Button, Input } from "./ui";
import type { RoleSkill } from "@/lib/types";

export const LEVELS = ["Missing", "Beginner", "Basic", "Intermediate", "Advanced", "Strong"];

export function SkillEditor({ skills, onChange, readOnly }: { skills: RoleSkill[]; onChange: (s: RoleSkill[]) => void; readOnly?: boolean }) {
  const update = (i: number, patch: Partial<RoleSkill>) => onChange(skills.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  return (
    <div className="space-y-2">
      <div className="hidden grid-cols-12 gap-2 text-xs muted md:grid">
        <span className="col-span-3">Skill</span><span className="col-span-2">Required level</span>
        <span className="col-span-2">Importance (0–1)</span><span className="col-span-4">Topics (comma separated)</span>
      </div>
      {skills.map((s, i) => (
        <div key={i} className="grid grid-cols-1 gap-2 rounded-lg border border-theme p-2 md:grid-cols-12 md:border-0 md:p-0">
          <Input className="md:col-span-3" value={s.skill} disabled={readOnly} placeholder="e.g. Machine Learning"
            onChange={(e) => update(i, { skill: e.target.value })} aria-label="Skill" />
          <select className="rounded-lg border border-theme bg-[var(--card)] px-2 py-2 text-sm md:col-span-2" disabled={readOnly}
            value={s.required_level} onChange={(e) => update(i, { required_level: Number(e.target.value) })} aria-label="Required level">
            {LEVELS.map((l, n) => <option key={n} value={n}>{n} – {l}</option>)}
          </select>
          <Input className="md:col-span-2" type="number" min={0} max={1} step={0.1} disabled={readOnly} value={s.importance_weight}
            onChange={(e) => update(i, { importance_weight: Number(e.target.value) })} aria-label="Importance" />
          <Input className="md:col-span-4" disabled={readOnly} value={s.topics.join(", ")} placeholder="Topics"
            onChange={(e) => update(i, { topics: e.target.value.split(",").map((t) => t.trim()).filter(Boolean) })} aria-label="Topics" />
          {!readOnly && (
            <Button variant="ghost" className="md:col-span-1" type="button" aria-label="Remove skill"
              onClick={() => onChange(skills.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></Button>
          )}
          {s.rationale && <p className="text-xs faint md:col-span-12">AI rationale: {s.rationale}</p>}
        </div>
      ))}
      {!readOnly && (
        <Button type="button" variant="secondary" onClick={() => onChange([...skills, { skill: "", required_level: 3, importance_weight: 0.7, topics: [], question_categories: [] }])}>
          <Plus className="h-4 w-4" /> Add skill
        </Button>
      )}
    </div>
  );
}

export const cleanSkills = (skills: RoleSkill[]) =>
  skills.filter((s) => s.skill.trim()).map((s) => ({ skill: s.skill.trim(), required_level: s.required_level,
    importance_weight: s.importance_weight, topics: s.topics, question_categories: s.question_categories ?? [] }));
