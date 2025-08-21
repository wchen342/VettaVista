import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogOverlay } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Pencil, Plus, X } from 'lucide-react'
import { SkillDataRow } from '../types/resume'
import { cn } from '@/lib/utils'
import { Input } from '@/components/ui/input'

interface SkillsEditorProps {
    skillRows: SkillDataRow[]
    onSkillsChange: (category: string, skills: string[]) => void
}

interface AddCategoryDialogProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    onAdd: (category: string, skills: string[]) => void
}

function AddCategoryDialog({ open, onOpenChange, onAdd }: AddCategoryDialogProps) {
    const [category, setCategory] = useState('')
    const [skills, setSkills] = useState<string[]>([])

    const handleSubmit = () => {
        if (category.trim()) {
            onAdd(category.trim(), skills)
            setCategory('')
            setSkills([])
            onOpenChange(false)
        }
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogOverlay className="bg-black/40" onClick={(e) => e.stopPropagation()} />
            <DialogContent className="sm:max-w-[500px] bg-background" onClick={(e) => e.stopPropagation()}>
                <DialogHeader>
                    <DialogTitle>Add New Skill Category</DialogTitle>
                </DialogHeader>
                <div className="space-y-4 py-4">
                    <div className="space-y-2">
                        <Label>Category Name</Label>
                        <Input
                            value={category}
                            onChange={(e) => setCategory(e.target.value)}
                            placeholder="e.g., Programming Languages, Tools, Frameworks"
                        />
                    </div>
                    <div className="space-y-2">
                        <Label>Skills (comma separated)</Label>
                        <Textarea
                            value={skills.join(', ')}
                            onChange={(e) => setSkills(e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                            placeholder="React, TypeScript, Node.js..."
                            className="h-[100px]"
                        />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)}>
                        <X className="h-4 w-4 mr-1" />
                        Cancel
                    </Button>
                    <Button onClick={handleSubmit} disabled={!category.trim()}>
                        Add Category
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

export function SkillsEditor({ skillRows, onSkillsChange }: SkillsEditorProps) {
    const [editingCategory, setEditingCategory] = useState<string | null>(null)
    const [editingSkills, setEditingSkills] = useState<string[]>([])
    const [showAddDialog, setShowAddDialog] = useState(false)

    const handleEditStart = (row: SkillDataRow) => {
        setEditingCategory(row.category)
        setEditingSkills(row.revisedSkills)
    }

    const handleEditSave = () => {
        if (editingCategory) {
            onSkillsChange(editingCategory, editingSkills)
            setEditingCategory(null)
        }
    }

    const handleEditCancel = () => {
        setEditingCategory(null)
        setEditingSkills([])
    }

    const handleAddNewCategory = (category: string, skills: string[]) => {
        onSkillsChange(category, skills)
    }

    return (
        <div className="space-y-4">
            <div className="flex justify-between items-center">
                <h3 className="text-lg font-semibold">Skills</h3>
                <Button variant="outline" size="sm" onClick={() => setShowAddDialog(true)}>
                    <Plus className="h-4 w-4 mr-1" />
                    Add Category
                </Button>
            </div>

            <div className="space-y-4">
                {skillRows.map(row => (
                    <div
                        key={row.id}
                        className={cn(
                            "rounded-lg border p-4",
                            row.status === 'new' && "border-green-200 bg-green-50/50",
                            row.status === 'removed' && "border-red-200 bg-red-50/50",
                            row.status === 'modified' && "border-yellow-200 bg-yellow-50/50"
                        )}
                    >
                        <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2">
                                <h4 className="font-medium">{row.category}</h4>
                                <Badge variant={row.status === 'unchanged' ? 'outline' : 'default'}>
                                    {row.status}
                                </Badge>
                            </div>
                            <Button variant="ghost" size="sm" onClick={() => handleEditStart(row)}>
                                <Pencil className="h-4 w-4" />
                            </Button>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="text-sm text-muted-foreground mb-1 block">Original</label>
                                <div className="flex flex-wrap gap-1">
                                    {row.originalSkills.map(skill => (
                                        <Badge key={skill} variant="secondary">
                                            {skill}
                                        </Badge>
                                    ))}
                                </div>
                            </div>

                            <div>
                                <label className="text-sm text-muted-foreground mb-1 block">Revised</label>
                                <div className="flex flex-wrap gap-1">
                                    {row.revisedSkills.map(skill => (
                                        <Badge
                                            key={skill}
                                            variant="default"
                                            className={cn(
                                                !row.originalSkills.includes(skill) && "bg-green-500",
                                                row.originalSkills.includes(skill) && "bg-primary"
                                            )}
                                        >
                                            {skill}
                                        </Badge>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            <Dialog open={editingCategory !== null} onOpenChange={(open) => !open && handleEditCancel()}>
                <DialogOverlay className="bg-black/40" onClick={(e) => e.stopPropagation()} />
                <DialogContent className="sm:max-w-[500px] bg-background" onClick={(e) => e.stopPropagation()}>
                    <DialogHeader>
                        <DialogTitle>Edit Skills - {editingCategory}</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                        <div className="space-y-2">
                            <Label>Skills (comma separated)</Label>
                            <Textarea
                                value={editingSkills.join(', ')}
                                onChange={(e) => setEditingSkills(e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                                placeholder="React, TypeScript, Node.js..."
                                className="h-[100px]"
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={handleEditCancel}>
                            <X className="h-4 w-4 mr-1" />
                            Cancel
                        </Button>
                        <Button onClick={handleEditSave}>
                            Save changes
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <AddCategoryDialog
                open={showAddDialog}
                onOpenChange={setShowAddDialog}
                onAdd={handleAddNewCategory}
            />
        </div>
    )
} 