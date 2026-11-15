import { mountFeatured } from './featured'
import { mountShelves } from './shelves'

const stage = document.querySelector<HTMLElement>('[data-feature-stage]')
if (stage) mountFeatured(stage)

const shelves = document.querySelector<HTMLElement>('.home-shelves')
if (shelves) mountShelves(shelves)
