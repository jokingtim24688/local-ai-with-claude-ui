using { /Fortnite.com/Devices }
using { /Fortnite.com/Characters }
using { /Fortnite.com/Game }
using { /Verse.org/Simulation }
using { /UnrealEngine.com/Temporary/Diagnostics }

# Night Crew: elimination rules. Drag this device into the level, then fill the
# @editable fields in its Details panel (ScoreManager, EndGame).
crescentisles_game := class(creative_device):
    @editable
    ScoreManager : score_manager_device = score_manager_device{}
    @editable
    EndGame : end_game_device = end_game_device{}

    ScoreToWin : int = 15
    var Scores : [agent]int = map{}

    OnBegin<override>()<suspends> : void =
        for (Player : GetPlayspace().GetPlayers(), FortCharacter := Player.GetFortCharacter[]):
            FortCharacter.EliminatedEvent().Subscribe(OnEliminated)
        GetPlayspace().PlayerAddedEvent().Subscribe(OnPlayerAdded)

    OnPlayerAdded(Player : player) : void =
        if (FortCharacter := Player.GetFortCharacter[]):
            FortCharacter.EliminatedEvent().Subscribe(OnEliminated)

    OnEliminated(Result : elimination_result) : void =
        if:
            Eliminator := Result.EliminatingCharacter?
            Agent := Eliminator.GetAgent[]
        then:
            ScoreManager.Activate(Agent)
            NewScore := (if (Old := Scores[Agent]) then Old else 0) + 1
            if (set Scores[Agent] = NewScore) {}
            Print("Elimination! Score: {NewScore}")
            if (NewScore >= ScoreToWin):
                EndGame.Activate(Agent)
