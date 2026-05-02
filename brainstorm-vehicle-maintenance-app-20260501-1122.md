# Brainstorm: vehicle-maintenance-app
Date: 2026-05-01 11:22
Technique(s) used: TBD

## [MAIN] vehicle-maintenance-app


## [MAIN] Vehicle Maintenance App

### User's Core Vision
- Personal use app
- Multi-vehicle support
- Recommended maintenance schedules by mileage/time interval
- Maintenance log with parts used

### Ideas — Free Association Round 1

- Mechanic in your pocket — describe a sound, it guesses what's wrong
- Car's diary — the vehicle narrates its own history
- Subscription alarm clock — nags like a dentist reminder for oil changes
- Resale value tracker — shows how maintenance affects car's worth
- Fleet manager for normal people — whole family's vehicles in one app
- Community-sourced service shop rater — Yelp filtered to your exact model
- Recall radar — auto-scans VIN against NHTSA, alerts before you know
- Warranty buddy — tracks what's still covered

### Ideas — Round 2 (Multi-vehicle + Schedule focus)


### Deep Dive: Schedule Engine Ideas

- Multiple independent clocks per service item (miles OR months, whichever first)
- Component-level tracking: brake pads, rotors, fluid each have own timers
- Part type affects interval (copper vs iridium spark plugs)
- Used car "unknown baseline" mode — mark services as confirmed/assumed
- Driving style adjustments: short trips, towing, dusty = shortened intervals
- Vehicle health percentage score — one glance dashboard
- Seasonal reminders: winter tires in Oct, A/C check in April
- Catch-up checklist for newly acquired vehicles
- Deferred service memory — skipped rotation gets remembered
- "Conservative / manufacturer / extended" interval philosophy modes


---
## [FORK 1] VIN and plate scan for instant vehicle setup
Parent: MAIN

- VIN sticker scan: zero typing, instant year/make/model/trim/engine
- License plate scan: lazy option, works from outside the car
- Windshield sticker OCR: reads mileage + date from oil change sticker
- Registration card photo: pulls mileage, expiry as bonus reminder
- VIN knows: engine type, transmission, AWD/4WD, towing package, warranty dates
- Auto-pull open NHTSA recalls on day one
- Auto-pull Technical Service Bulletins (TSBs) for known issues
- Manufacturer's exact maintenance schedule for specific trim

### Instant Setup Experience Ideas


---
## Final Summary

### Key Themes
1. **Instant, frictionless setup** — VIN/plate scan, odometer OCR, auto-populated schedules
2. **Smart scheduling engine** — dual triggers (miles + time), component-level clocks, driving style adjustments
3. **Multi-vehicle household** — health scores, family sharing, cost comparisons
4. **Trust through data** — NHTSA recalls, TSBs, used car baseline mode
5. **Longitudinal value** — parts logging, cost tracking, maintenance history export

### Forks Explored
- FORK 1: VIN and plate scan for instant vehicle setup

### Ideas Generated: 20
### Techniques Used: Free Association
