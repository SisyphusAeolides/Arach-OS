module ImageComposition

%default total

public export
data Trust = Unpinned | Pinned

public export
data Stage = Boot | Core | Desktop | Installer

public export
record Component where
  constructor MkComponent
  name : String
  revision : String
  trust : Trust

public export
data Admitted : Component -> Type where
  ExactPin : {name, revision : String} ->
             Admitted (MkComponent name revision Pinned)

public export
admit : (component : Component) -> Maybe (Admitted component)
admit (MkComponent name revision Unpinned) = Nothing
admit (MkComponent name revision Pinned) = Just ExactPin

public export
data Ready : Stage -> Type where
  BootReady : Ready Boot
  CoreReady : Ready Boot -> Ready Core
  DesktopReady : Ready Core -> Ready Desktop
  InstallerReady : Ready Desktop -> Ready Installer

public export
record BuildPlan where
  constructor MkBuildPlan
  component : Component
  admitted : Admitted component
  stage : Stage
  ready : Ready stage

public export
nextStage : Stage -> Maybe Stage
nextStage Boot = Just Core
nextStage Core = Just Desktop
nextStage Desktop = Just Installer
nextStage Installer = Nothing

public export
unpinnedCannotCompose :
  {componentName, componentRevision : String} ->
  Admitted (MkComponent componentName componentRevision Unpinned) -> Void
unpinnedCannotCompose value impossible

public export
data Journal = Absent | Durable

public export
data Mutation = Clean | Changed

public export
data Transaction : Journal -> Mutation -> Type where
  Fresh : Transaction Absent Clean
  Prepared : Transaction Durable Clean
  Applied : Transaction Durable Changed
  Verified : Transaction Durable Changed
  RolledBack : Transaction Durable Clean

public export
prepare : Transaction Absent Clean -> Transaction Durable Clean
prepare Fresh = Prepared

public export
apply : Transaction Durable Clean -> Transaction Durable Changed
apply Prepared = Applied
apply RolledBack = Applied

public export
verify : Transaction Durable Changed -> Transaction Durable Changed
verify Applied = Verified
verify Verified = Verified

public export
noMutationWithoutJournal : Transaction Absent Changed -> Void
noMutationWithoutJournal value impossible

public export
data HandoffField
  = Firmware | Partition | Locale | Region | Zone
  | Keyboard | Username | Fullname | Hostname

public export
data Secret = Password | RootPassword | LuksPassphrase

public export
data Crosses : Secret -> HandoffField -> Type where

public export
secretCannotCross : Crosses secret field -> Void
secretCannotCross value impossible
