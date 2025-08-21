export interface Education {
    degree: string
    university: string
    extra: string
    start: string  // YYYY-MM format
    graduation: string  // YYYY-MM format
}

export interface ExperienceEntry {
    title: string
    start: string  // YYYY-MM format
    end: string  // YYYY-MM format or "Present"
    organization: string
    location: string
    details: string[]
    _exp_id: string
}

export interface ProjectEntry {
    name: string
    details: string[]
    _proj_id: string
}

export interface ResumeModel {
    skills: Record<string, string[]>
    preferred_titles: string[]
    bad_words: string[]
    experience: ExperienceEntry[]
    projects: ProjectEntry[]
}

export type EditableSection =
    | { type: 'experience'; detail_index: number }
    | { type: 'project'; detail_index: number }

export interface SkillDataRow {
    id: string
    category: string
    originalSkills: string[]
    revisedSkills: string[]
    status: 'new' | 'removed' | 'modified' | 'unchanged'
}