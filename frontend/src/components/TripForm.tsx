import { Loader2Icon } from 'lucide-react'
import { type FormEvent, type ReactNode, useState } from 'react'
import type { IntervalOption, Place, TripPlanRequest } from '@/api/types'
import { PlaceCombobox } from '@/components/PlaceCombobox'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { addDays, nextFullHour, toDateTimeLocal } from '@/lib/format'

// Same limits as the backend validation.
const MAX_LOAD_LB = 80_000
const MAX_DAYS_AHEAD = 7

const INTERVAL_OPTIONS: Array<{ value: IntervalOption; label: string }> = [
  { value: 'auto', label: 'Auto' },
  { value: 10, label: 'Every 10 mi' },
  { value: 25, label: 'Every 25 mi' },
  { value: 50, label: 'Every 50 mi' },
]

interface FormValues {
  origin: Place | null
  destination: Place | null
  departure: string // datetime-local value
  weight: string
}

type FormErrors = Partial<Record<keyof FormValues, string>>

function validate({ origin, destination, departure, weight }: FormValues): FormErrors {
  const errors: FormErrors = {}
  if (!origin) errors.origin = 'Choose an origin.'
  if (!destination) errors.destination = 'Choose a destination.'
  if (origin && destination && origin.lat === destination.lat && origin.lon === destination.lon) {
    errors.destination = 'Destination must be different from the origin.'
  }

  const departureDate = new Date(departure)
  const now = new Date()
  if (Number.isNaN(departureDate.getTime())) errors.departure = 'Choose a departure date and time.'
  else if (departureDate < new Date(now.getTime() - 60 * 60 * 1000)) errors.departure = 'Departure cannot be in the past.'
  else if (departureDate > addDays(now, MAX_DAYS_AHEAD)) errors.departure = 'Departure must be within the next 7 days.'

  const pounds = Number(weight)
  if (!weight || !Number.isFinite(pounds) || pounds <= 0 || pounds > MAX_LOAD_LB) {
    errors.weight = `Enter a load between 1 and ${MAX_LOAD_LB.toLocaleString('en-US')} lb.`
  }
  return errors
}

interface TripFormProps {
  loading: boolean
  onSubmit: (trip: TripPlanRequest) => void
}

export function TripForm({ loading, onSubmit }: TripFormProps) {
  const [values, setValues] = useState<FormValues>(() => ({
    origin: null,
    destination: null,
    departure: toDateTimeLocal(nextFullHour()),
    weight: '40000',
  }))
  const [intervalMiles, setIntervalMiles] = useState<IntervalOption>('auto')
  const [errors, setErrors] = useState<FormErrors>({})
  // Bounds for the date picker; submit-time validation uses the current time.
  const [openedAt] = useState(() => new Date())

  function update<K extends keyof FormValues>(field: K, value: FormValues[K]) {
    setValues((current) => ({ ...current, [field]: value }))
    setErrors((current) => ({ ...current, [field]: undefined }))
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const found = validate(values)
    setErrors(found)
    if (Object.values(found).some(Boolean) || !values.origin || !values.destination) return
    onSubmit({
      origin: values.origin,
      destination: values.destination,
      departure_time: new Date(values.departure).toISOString(),
      load_weight_lb: Number(values.weight),
      interval_miles: intervalMiles,
    })
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <Field id="origin" label="Origin" error={errors.origin}>
        <PlaceCombobox
          id="origin"
          value={values.origin}
          onChange={(place) => update('origin', place)}
          placeholder="Where does the trip start?"
          invalid={Boolean(errors.origin)}
        />
      </Field>

      <Field id="destination" label="Destination" error={errors.destination}>
        <PlaceCombobox
          id="destination"
          value={values.destination}
          onChange={(place) => update('destination', place)}
          placeholder="Where is it going?"
          invalid={Boolean(errors.destination)}
        />
      </Field>

      <Field id="departure" label="Departure" error={errors.departure}>
        <Input
          id="departure"
          type="datetime-local"
          value={values.departure}
          min={toDateTimeLocal(openedAt)}
          max={toDateTimeLocal(addDays(openedAt, MAX_DAYS_AHEAD))}
          onChange={(event) => update('departure', event.target.value)}
          aria-invalid={Boolean(errors.departure)}
        />
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field id="weight" label="Load weight (lb)" error={errors.weight}>
          <Input
            id="weight"
            type="number"
            inputMode="numeric"
            min={1}
            max={MAX_LOAD_LB}
            step={500}
            value={values.weight}
            onChange={(event) => update('weight', event.target.value)}
            aria-invalid={Boolean(errors.weight)}
          />
        </Field>

        <Field id="interval" label="Weather checkpoints">
          <Select
            value={String(intervalMiles)}
            onValueChange={(value) => setIntervalMiles(value === 'auto' ? 'auto' : (Number(value) as IntervalOption))}
          >
            <SelectTrigger id="interval" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {INTERVAL_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={String(option.value)}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      </div>

      <div className="flex flex-col gap-1.5">
        <Button type="submit" size="lg" disabled={loading}>
          {loading && <Loader2Icon className="animate-spin" />}
          {loading ? 'Checking routes and weather…' : 'Find safest route'}
        </Button>
        {loading && (
          <p className="text-center text-xs text-muted-foreground">
            Comparing 3 truck routes against the forecast usually takes 10–20 s.
          </p>
        )}
      </div>
    </form>
  )
}

interface FieldProps {
  id: string
  label: string
  error?: string
  children: ReactNode
}

function Field({ id, label, error, children }: FieldProps) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}
