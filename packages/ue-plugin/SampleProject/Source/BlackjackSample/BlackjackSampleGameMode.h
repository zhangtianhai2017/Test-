#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "BlackjackSampleGameMode.generated.h"

/**
 * Demo GameMode: on BeginPlay, places an ABlackjackTableActor in the level,
 * binds the component's OnBigWin → camera shake + log, and wires simple input
 * (Space = Deal, H/S/D/P = Hit/Stand/Double/Split). This gives you a playable
 * 3D demo without requiring any pre-built Blueprint .uassets.
 *
 * In a real game you'd replace this with a Blueprint GameMode that references
 * custom Blueprint actors (BP_CasinoTable, BP_DealerNPC, BP_CardMesh_Premium).
 */
UCLASS()
class BLACKJACKSAMPLE_API ABlackjackSampleGameMode : public AGameModeBase
{
    GENERATED_BODY()

public:
    ABlackjackSampleGameMode();

protected:
    virtual void BeginPlay() override;
};
