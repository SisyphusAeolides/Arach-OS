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
