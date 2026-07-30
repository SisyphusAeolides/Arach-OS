{-# OPTIONS --safe --without-K #-}
module ImageComposition where

open import Agda.Builtin.Equality using (_≡_; refl)

data Trust : Set where
  unpinned pinned : Trust

data Stage : Set where
  boot core desktop installer : Stage

record Component : Set where
  constructor component
  field
    trust : Trust

data Admitted : Component → Set where
  exact-pin : Admitted (component pinned)

data Ready : Stage → Set where
  boot-ready : Ready boot
  core-ready : Ready boot → Ready core
  desktop-ready : Ready core → Ready desktop
  installer-ready : Ready desktop → Ready installer

record BuildPlan : Set where
  constructor plan
  field
    target : Component
    admitted : Admitted target
    stage : Stage
    ready : Ready stage

data ⊥ : Set where

unpinned-cannot-compose : Admitted (component unpinned) → ⊥
unpinned-cannot-compose ()

installer-requires-desktop : (proof : Ready installer) →
                             Ready desktop
installer-requires-desktop (installer-ready proof) = proof

exact-pin-unique : (proof : Admitted (component pinned)) →
                   proof ≡ exact-pin
exact-pin-unique exact-pin = refl
