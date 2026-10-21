import { ChevronsUpDownIcon, MapPinIcon } from 'lucide-react'
import { useState } from 'react'
import type { Place } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { usePlaceSearch } from '@/hooks/usePlaceSearch'
import { cn } from '@/lib/utils'

interface PlaceComboboxProps {
  id: string
  value: Place | null
  onChange: (place: Place) => void
  placeholder: string
  invalid?: boolean
}

export function PlaceCombobox({ id, value, onChange, placeholder, invalid }: PlaceComboboxProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const { results, loading, tooShort } = usePlaceSearch(query)

  function select(place: Place) {
    onChange(place)
    setOpen(false)
    setQuery('')
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          aria-invalid={invalid}
          className="w-full justify-between font-normal"
        >
          <span className={cn('truncate', !value && 'text-muted-foreground')}>{value?.label ?? placeholder}</span>
          <ChevronsUpDownIcon className="opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-(--radix-popover-trigger-width) p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput value={query} onValueChange={setQuery} placeholder="Search a city or address…" />
          <CommandList>
            {loading && results.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">Searching…</p>
            ) : (
              <CommandEmpty>{tooShort ? 'Type at least 2 characters.' : 'No places found.'}</CommandEmpty>
            )}
            {results.map((place) => (
              <CommandItem
                key={`${place.label}-${place.lat}-${place.lon}`}
                value={`${place.label}-${place.lat}-${place.lon}`}
                onSelect={() => select(place)}
              >
                <MapPinIcon className="text-muted-foreground" />
                <span className="truncate">{place.label}</span>
              </CommandItem>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
