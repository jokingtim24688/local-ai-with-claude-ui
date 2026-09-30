using { /Fortnite.com/Devices }
using { /Verse.org/Simulation }
using { /UnrealEngine.com/Temporary/Diagnostics }

# Crescent Isles high ground: whoever steps onto the empty peak first gets the granter's item.
crescent_highground := class(creative_device):
    @editable
    Peak : mutator_zone_device = mutator_zone_device{}
    @editable
    Reward : item_granter_device = item_granter_device{}
    var Holders : int = 0

    OnBegin<override>()<suspends> : void =
        Peak.AgentEntersEvent.Subscribe(OnEnter)
        Peak.AgentExitsEvent.Subscribe(OnExit)

    OnEnter(Agent : agent) : void =
        set Holders += 1
        if (Holders = 1):
            Reward.GrantItem(Agent)
            Print("High ground taken")

    OnExit(Agent : agent) : void =
        if (Holders > 0):
            set Holders -= 1
