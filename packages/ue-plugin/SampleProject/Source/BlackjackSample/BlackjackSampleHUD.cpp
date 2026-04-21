#include "BlackjackSampleHUD.h"

#include "BlackjackSamplePlayerController.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "Engine/GameInstance.h"
#include "GameFramework/PlayerController.h"

ABlackjackSampleHUD::ABlackjackSampleHUD()
{
    PrimaryActorTick.bCanEverTick = true;
}

void ABlackjackSampleHUD::BeginPlay()
{
    Super::BeginPlay();

    if (UBlackjackNetClient* Net = GetNetClient())
    {
        Net->OnConnectionStateChanged.AddDynamic(this, &ABlackjackSampleHUD::HandleConnectionStateChanged);
        Net->OnPhaseChanged.AddDynamic(this, &ABlackjackSampleHUD::HandlePhaseChanged);
        Net->OnBankrollChanged.AddDynamic(this, &ABlackjackSampleHUD::HandleBankrollChanged);
        Net->OnTableState.AddDynamic(this, &ABlackjackSampleHUD::HandleTableState);
        Net->OnDealerQuip.AddDynamic(this, &ABlackjackSampleHUD::HandleDealerQuip);

        // Prime cached connection state in case events already fired.
        ConnectionState = Net->GetConnectionState();
    }
}

void ABlackjackSampleHUD::EndPlay(const EEndPlayReason::Type Reason)
{
    if (UBlackjackNetClient* Net = GetNetClient())
    {
        Net->OnConnectionStateChanged.RemoveDynamic(this, &ABlackjackSampleHUD::HandleConnectionStateChanged);
        Net->OnPhaseChanged.RemoveDynamic(this, &ABlackjackSampleHUD::HandlePhaseChanged);
        Net->OnBankrollChanged.RemoveDynamic(this, &ABlackjackSampleHUD::HandleBankrollChanged);
        Net->OnTableState.RemoveDynamic(this, &ABlackjackSampleHUD::HandleTableState);
        Net->OnDealerQuip.RemoveDynamic(this, &ABlackjackSampleHUD::HandleDealerQuip);
    }
    Super::EndPlay(Reason);
}

void ABlackjackSampleHUD::DrawHUD()
{
    Super::DrawHUD();
    if (!Canvas) return;

    UFont* Font = GEngine ? GEngine->GetMediumFont() : nullptr;
    if (!Font) return;

    const FLinearColor White(1.f, 1.f, 1.f, 1.f);
    const FLinearColor Yellow(1.f, 0.95f, 0.2f, 1.f);
    const float X = 24.f;
    float Y = 24.f;
    const float Line = 22.f;

    int32 SeatIdx = -1;
    if (const ABlackjackSamplePlayerController* PC = Cast<ABlackjackSamplePlayerController>(GetOwningPlayerController()))
    {
        SeatIdx = PC->ClaimedSeatIndex;
    }

    const FString Row1 = FString::Printf(TEXT("Blackjack Sample (UE 5.6)"));
    const FString Row2 = FString::Printf(TEXT("Connection: %s"), *ConnStateToString(ConnectionState));
    const FString Row3 = FString::Printf(TEXT("Phase: %s    ActiveSeat: %d"),
                                         *PhaseToString(Phase), ActiveSeatIndex);
    const FString Row4 = FString::Printf(TEXT("My Seat: %d    Bankroll: $%d"), SeatIdx, LocalBankroll);
    const FString Row5 = FString::Printf(TEXT("Dealer: %s"),
                                         LastDealerQuip.IsEmpty() ? TEXT("(silence)") : *LastDealerQuip);
    const FString Row6 = TEXT("Keys: 1/2/3 bet 5/25/100, H hit, S stand, D double, P split, R surrender, N new round");
    const FString Row7 = TEXT("Gestures: C confident, X nervous, O pokerface, T taunt, G sigh, V celebrate");

    Canvas->DrawText(Font, Row1, X, Y, 1.f, 1.f, FFontRenderInfo()); Y += Line;
    Canvas->DrawText(Font, Row2, X, Y, 1.f, 1.f, FFontRenderInfo()); Y += Line;
    Canvas->DrawText(Font, Row3, X, Y, 1.f, 1.f, FFontRenderInfo()); Y += Line;
    Canvas->DrawText(Font, Row4, X, Y, 1.f, 1.f, FFontRenderInfo()); Y += Line;
    Canvas->DrawText(Font, Row5, X, Y, 1.f, 1.f, FFontRenderInfo()); Y += Line + 8.f;
    Canvas->DrawText(Font, Row6, X, Y, 1.f, 1.f, FFontRenderInfo()); Y += Line;
    Canvas->DrawText(Font, Row7, X, Y, 1.f, 1.f, FFontRenderInfo());
    // Yellow emphasis colour intentionally unused by DrawText(UFont, ...) signature
    // in some engine versions; callers can switch to DrawColoredText via a child.
    (void)White; (void)Yellow;
}

// ---------------------------------------------------------------------------
// Delegate handlers — just cache into member state for next DrawHUD frame.
// ---------------------------------------------------------------------------

void ABlackjackSampleHUD::HandleConnectionStateChanged(EBlackjackConnectionState NewState)
{
    ConnectionState = NewState;
}

void ABlackjackSampleHUD::HandlePhaseChanged(EBlackjackPhase NewPhase)
{
    Phase = NewPhase;
}

void ABlackjackSampleHUD::HandleBankrollChanged(int32 SeatIndex, int32 NewBalance, int32 /*Delta*/)
{
    int32 MySeat = -1;
    if (const ABlackjackSamplePlayerController* PC = Cast<ABlackjackSamplePlayerController>(GetOwningPlayerController()))
    {
        MySeat = PC->ClaimedSeatIndex;
    }
    if (SeatIndex == MySeat)
    {
        LocalBankroll = NewBalance;
    }
}

void ABlackjackSampleHUD::HandleTableState(const FBlackjackTableStateSnapshot& Snapshot)
{
    Phase = Snapshot.Phase;
    ActiveSeatIndex = Snapshot.ActiveSeatIndex;

    int32 MySeat = -1;
    if (const ABlackjackSamplePlayerController* PC = Cast<ABlackjackSamplePlayerController>(GetOwningPlayerController()))
    {
        MySeat = PC->ClaimedSeatIndex;
    }
    if (MySeat >= 0)
    {
        for (const FBlackjackSeatPayload& Seat : Snapshot.Seats)
        {
            if (Seat.Index == MySeat)
            {
                LocalBankroll = Seat.Bankroll;
                break;
            }
        }
    }
}

void ABlackjackSampleHUD::HandleDealerQuip(const FString& Text, const FString& /*Tone*/, const FString& /*Language*/, const FString& /*AudioUrl*/)
{
    LastDealerQuip = Text;
}

// ---------------------------------------------------------------------------

UBlackjackNetClient* ABlackjackSampleHUD::GetNetClient() const
{
    const UGameInstance* GI = GetGameInstance();
    return GI ? GI->GetSubsystem<UBlackjackNetClient>() : nullptr;
}

FString ABlackjackSampleHUD::PhaseToString(EBlackjackPhase InPhase)
{
    switch (InPhase)
    {
    case EBlackjackPhase::Betting:     return TEXT("Betting");
    case EBlackjackPhase::Dealing:     return TEXT("Dealing");
    case EBlackjackPhase::Insurance:   return TEXT("Insurance");
    case EBlackjackPhase::PlayerTurn:  return TEXT("PlayerTurn");
    case EBlackjackPhase::DealerTurn:  return TEXT("DealerTurn");
    case EBlackjackPhase::Settlement:  return TEXT("Settlement");
    case EBlackjackPhase::RoundOver:   return TEXT("RoundOver");
    }
    return TEXT("?");
}

FString ABlackjackSampleHUD::ConnStateToString(EBlackjackConnectionState InState)
{
    switch (InState)
    {
    case EBlackjackConnectionState::Disconnected:    return TEXT("Disconnected");
    case EBlackjackConnectionState::Connecting:      return TEXT("Connecting");
    case EBlackjackConnectionState::Awaiting_Hello:  return TEXT("Awaiting HELLO");
    case EBlackjackConnectionState::Connected:       return TEXT("Connected");
    case EBlackjackConnectionState::Reconnecting:    return TEXT("Reconnecting");
    case EBlackjackConnectionState::Closed:          return TEXT("Closed");
    }
    return TEXT("?");
}
