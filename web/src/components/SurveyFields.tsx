import type { Field } from '../data/surveys'

type Props = {
  fields: Field[]
  values: Record<string, string>
  onChange: (id: string, value: string) => void
}

export function SurveyFields({ fields, values, onChange }: Props) {
  return (
    <>
      {fields.map((field) => (
        <div className="field" key={field.id}>
          <label htmlFor={field.id}>{field.label}</label>
          {field.type === 'select' ? (
            <select
              id={field.id}
              value={values[field.id] || ''}
              onChange={(e) => onChange(field.id, e.target.value)}
              required={field.required}
            >
              <option value="">Select…</option>
              {(field.options || []).map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          ) : field.type === 'textarea' ? (
            <textarea
              id={field.id}
              value={values[field.id] || ''}
              placeholder={field.placeholder}
              onChange={(e) => onChange(field.id, e.target.value)}
              required={field.required}
            />
          ) : (
            <input
              id={field.id}
              value={values[field.id] || ''}
              placeholder={field.placeholder}
              onChange={(e) => onChange(field.id, e.target.value)}
              required={field.required}
            />
          )}
        </div>
      ))}
    </>
  )
}

export function fieldsComplete(fields: Field[], values: Record<string, string>) {
  return fields.every((field) => !field.required || Boolean((values[field.id] || '').trim()))
}
