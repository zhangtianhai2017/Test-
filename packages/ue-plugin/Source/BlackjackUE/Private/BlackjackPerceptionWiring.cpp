#include "BlackjackPerceptionWiring.h"

#include "BlackjackNetClient.h"
#include "BlackjackTellSubsystem.h"
#include "BlackjackTrustSubsystem.h"
#include "Engine/GameInstance.h"
#include "Engine/World.h"

void UBlackjackPerceptionWiring::InstallPerceptionWiring(UObject* WorldContextObject)
{
    if (!WorldContextObject)
    {
        UE_LOG(LogTemp, Warning, TEXT("[BlackjackPerception] InstallPerceptionWiring: null WorldContextObject"));
        return;
    }

    UWorld* World = WorldContextObject->GetWorld();
    if (!World)
    {
        UE_LOG(LogTemp, Warning, TEXT("[BlackjackPerception] InstallPerceptionWiring: no World from context"));
        return;
    }

    UGameInstance* GI = World->GetGameInstance();
    if (!GI)
    {
        UE_LOG(LogTemp, Warning, TEXT("[BlackjackPerception] InstallPerceptionWiring: no GameInstance"));
        return;
    }

    UBlackjackNetClient* NetClient = GI->GetSubsystem<UBlackjackNetClient>();
    UBlackjackTellSubsystem* TellSubsystem = GI->GetSubsystem<UBlackjackTellSubsystem>();
    // Resolved for side-effect of ensuring the subsystem exists; no auto-bind
    // target in the v1 protocol (see TODO below).
    UBlackjackTrustSubsystem* TrustSubsystem = GI->GetSubsystem<UBlackjackTrustSubsystem>();

    if (!NetClient || !TellSubsystem)
    {
        UE_LOG(LogTemp, Warning, TEXT("[BlackjackPerception] InstallPerceptionWiring: missing NetClient or TellSubsystem"));
        return;
    }

    // Wire the tell registry directly to gesture events. The handler lives
    // on the subsystem itself so we avoid a helper-UObject stash.
    // AddUniqueDynamic prevents double-binding if BeginPlay runs twice
    // (e.g. seamless travel / PIE restart).
    NetClient->OnGestureMade.AddUniqueDynamic(TellSubsystem, &UBlackjackTellSubsystem::HandleGestureMade);

    // TODO(M8): no bluff-outcome frames exist in the v1 protocol, so the
    // trust subsystem is left for designers to drive via
    // UBlackjackTrustSubsystem::ApplyBluffOutcome from gameplay Blueprints.
    (void)TrustSubsystem;

    UE_LOG(LogTemp, Log, TEXT("[BlackjackPerception] Perception wiring installed (tells: auto, trust: manual)"));
}
