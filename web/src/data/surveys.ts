export type Field = {
  id: string
  label: string
  type: 'text' | 'select' | 'textarea'
  placeholder?: string
  options?: string[]
  required?: boolean
}

export const lessonsProfileFields: Field[] = [
  {
    id: 'name',
    label: 'Your name',
    type: 'text',
    placeholder: 'Alex Rivera',
    required: true,
  },
  {
    id: 'role',
    label: 'Role on the project',
    type: 'select',
    options: [
      'Project Manager',
      'Superintendent',
      'Project Engineer',
      'Owner / CM',
      'Trade Partner',
      'Executive / Sponsor',
      'Other',
    ],
    required: true,
  },
  {
    id: 'company',
    label: 'Company',
    type: 'text',
    placeholder: 'Acme Construction',
    required: true,
  },
  {
    id: 'project',
    label: 'Project name',
    type: 'text',
    placeholder: 'Central Campus Phase 2',
    required: true,
  },
  {
    id: 'projectType',
    label: 'Project type',
    type: 'select',
    options: [
      'Healthcare',
      'Education',
      'Commercial',
      'Industrial',
      'Infrastructure',
      'Residential / Multifamily',
      'Other',
    ],
    required: true,
  },
  {
    id: 'contract',
    label: 'Delivery method',
    type: 'select',
    options: ['Design-Bid-Build', 'CMAR', 'Design-Build', 'IPD', 'Other'],
    required: true,
  },
]

export const lessonsCloseoutQuestions: Field[] = [
  {
    id: 'outcome',
    label: 'In one paragraph, how did this project actually finish versus the plan?',
    type: 'textarea',
    required: true,
  },
  {
    id: 'win',
    label: 'What is the single biggest win the team should repeat?',
    type: 'textarea',
    required: true,
  },
  {
    id: 'pain',
    label: 'What caused the most pain, delay, or cost growth?',
    type: 'textarea',
    required: true,
  },
  {
    id: 'coordination',
    label: 'Where did coordination break down (trades, design, owner, utilities, etc.)?',
    type: 'textarea',
    required: true,
  },
  {
    id: 'information',
    label: 'What information arrived too late — or never arrived cleanly?',
    type: 'textarea',
    required: true,
  },
  {
    id: 'buyout',
    label: 'What buyout / procurement decisions would you make differently?',
    type: 'textarea',
    required: true,
  },
  {
    id: 'safety',
    label: 'Any safety, quality, or field condition lessons that must be captured?',
    type: 'textarea',
    required: true,
  },
  {
    id: 'handoff',
    label: 'What should the next project team know on day one?',
    type: 'textarea',
    required: true,
  },
]

export const mentorProfileFields: Field[] = [
  {
    id: 'name',
    label: 'Your name',
    type: 'text',
    placeholder: 'Jordan Lee',
    required: true,
  },
  {
    id: 'role',
    label: 'Your role',
    type: 'select',
    options: [
      'Project Manager',
      'Superintendent',
      'Estimator / Precon',
      'Project Executive',
      'Owner / Developer',
      'Design Partner',
      'Other',
    ],
    required: true,
  },
  {
    id: 'experience',
    label: 'Years in construction',
    type: 'select',
    options: ['0–3', '4–8', '9–15', '16+'],
    required: true,
  },
  {
    id: 'focus',
    label: 'What are you looking for today?',
    type: 'select',
    options: [
      'Risk judgment on a live decision',
      'How to handle a tough conversation',
      'Buyout / procurement advice',
      'Schedule recovery thinking',
      'Closeout / lessons guidance',
      'Something else',
    ],
    required: true,
  },
]

export const mentorFollowups: Field[] = [
  {
    id: 'stakes',
    label: 'What happens if this goes poorly in the next 30 days?',
    type: 'textarea',
    required: true,
  },
  {
    id: 'constraints',
    label: 'What constraints are fixed (budget, contract, politics, schedule)?',
    type: 'textarea',
    required: true,
  },
  {
    id: 'tried',
    label: 'What have you already tried?',
    type: 'textarea',
    required: true,
  },
]
