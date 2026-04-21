// Pure-C++ PlayerController for the Blackjack SampleProject.
// All EnhancedInput IMC / IA assets are constructed at runtime via NewObject<>
// so the sample project ships no .uasset files. Validated against UE 5.6.

#include "BlackjackSamplePlayerController.h"

#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "InputTriggers.h"
#include "Engine/GameInstance.h"
#include "Engine/LocalPlayer.h"

ABlackjackSamplePlayerController::ABlackjackSamplePlayerController()
{
    // Use the default camera manager (no custom camera logic; pawn has the camera).
    PlayerCameraManagerClass = APlayerCameraManager::StaticClass();
}

void ABlackjackSamplePlayerController::BeginPlay()
{
    Super::BeginPlay();

    BuildInputMappings();
    ActivateInputMapping();

    // Track our seat assignment so action handlers know which seat index to send.
    if (UBlackjackNetClient* Net = GetNetClient())
    {
        Net->OnSeatAssigned.AddDynamic(this, &ABlackjackSamplePlayerController::HandleSeatAssigned);
        Net->OnSeatReleased.AddDynamic(this, &ABlackjackSamplePlayerController::HandleSeatReleased);
    }
}

void ABlackjackSamplePlayerController::EndPlay(const EEndPlayReason::Type Reason)
{
    if (UBlackjackNetClient* Net = GetNetClient())
    {
        Net->OnSeatAssigned.RemoveDynamic(this, &ABlackjackSamplePlayerController::HandleSeatAssigned);
        Net->OnSeatReleased.RemoveDynamic(this, &ABlackjackSamplePlayerController::HandleSeatReleased);
    }

    // Release the root pin so GC can reclaim IMC/IAs on shutdown.
    if (InputMapping && InputMapping->IsRooted())
    {
        InputMapping->RemoveFromRoot();
    }

    Super::EndPlay(Reason);
}

void ABlackjackSamplePlayerController::SetupInputComponent()
{
    Super::SetupInputComponent();

    UEnhancedInputComponent* EIC = Cast<UEnhancedInputComponent>(InputComponent);
    if (!EIC)
    {
        return;
    }
    if (!InputMapping)
    {
        BuildInputMappings();
    }

    // Bind each IA to its handler. ETriggerEvent::Triggered fires on the press
    // frame for a pressed-key trigger, matching classic "keyboard shortcut" feel.
    EIC->BindAction(IA_Bet5,              ETriggerEvent::Triggered, this, &ABlackjackSamplePlayerController::HandleBet5);
    EIC->BindAction(IA_Bet25,             ETriggerEvent::Triggered, this, &ABlackjackSamplePlayerController::HandleBet25);
    EIC->BindAction(IA_Bet100,            ETriggerEvent::Triggered, this, &ABlackjackSamplePlayerController::HandleBet100);
    EIC->BindAction(IA_Hit,               ETriggerEvent::Triggered, this, &ABlackjackSamplePlayerController::HandleHit);
    EIC->BindAction(IA_Stand,             ETriggerEvent::Triggered, this, &ABlackjackSamplePlayerController::HandleStand);
    EIC->BindAction(IA_Double,            ETriggerEvent::Triggered, this, &ABlackjackSamplePlayerController::HandleDouble);
    EIC->BindAction(IA_Split,             ETriggerEvent::Triggered, this, &ABlackjackSamplePlayerController::HandleSplit);
    EIC->BindAction(IA_Surrender,         ETriggerEvent::Triggered, this, &ABlackjackSamplePlayerController::HandleSurrender);
    EIC->BindAction(IA_NewRound,          ETriggerEvent::Triggered, this, &ABlackjackSamplePlayerController::HandleNewRound);
    EIC->BindAction(IA_GestureConfident,  ETriggerEvent::Triggered, this, &ABlackjackSamplePlayerController::HandleGestureConfident);
    EIC->BindAction(IA_GestureNervous,    ETriggerEvent::Triggered, this, &ABlackjackSamplePlayerController::HandleGestureNervous);
    EIC->BindAction(IA_GesturePokerFace,  ETriggerEvent::Triggered, this, &ABlackjackSamplePlayerController::HandleGesturePokerFace);
    EIC->BindAction(IA_GestureTaunt,      ETriggerEvent::Triggered, this, &ABlackjackSamplePlayerController::HandleGestureTaunt);
    EIC->BindAction(IA_GestureSigh,       ETriggerEvent::Triggered, this, &ABlackjackSamplePlayerController::HandleGestureSigh);
    EIC->BindAction(IA_GestureCelebrate,  ETriggerEvent::Triggered, this, &ABlackjackSamplePlayerController::HandleGestureCelebrate);
}

// ---------------------------------------------------------------------------
// IMC / IA construction — entirely at runtime via NewObject<>.
// Anchor the IMC at the root set so GC can't collect it between BeginPlay and
// EndPlay (UPROPERTY pointers aren't enough for transient EnhancedInput assets
// referenced only from a subsystem). Children + IAs stay alive through the IMC.
// ---------------------------------------------------------------------------

static UInputAction* MakeBoolAction(UObject* Outer, const TCHAR* Name)
{
    UInputAction* IA = NewObject<UInputAction>(Outer, Name);
    IA->ValueType = EInputActionValueType::Boolean;
    return IA;
}

void ABlackjackSamplePlayerController::BuildInputMappings()
{
    if (InputMapping) return;

    InputMapping = NewObject<UInputMappingContext>(this, TEXT("BlackjackSampleIMC"));
    InputMapping->AddToRoot();

    IA_Bet5              = MakeBoolAction(this, TEXT("IA_Bet5"));
    IA_Bet25             = MakeBoolAction(this, TEXT("IA_Bet25"));
    IA_Bet100            = MakeBoolAction(this, TEXT("IA_Bet100"));
    IA_Hit               = MakeBoolAction(this, TEXT("IA_Hit"));
    IA_Stand             = MakeBoolAction(this, TEXT("IA_Stand"));
    IA_Double            = MakeBoolAction(this, TEXT("IA_Double"));
    IA_Split             = MakeBoolAction(this, TEXT("IA_Split"));
    IA_Surrender         = MakeBoolAction(this, TEXT("IA_Surrender"));
    IA_NewRound          = MakeBoolAction(this, TEXT("IA_NewRound"));
    IA_GestureConfident  = MakeBoolAction(this, TEXT("IA_GestureConfident"));
    IA_GestureNervous    = MakeBoolAction(this, TEXT("IA_GestureNervous"));
    IA_GesturePokerFace  = MakeBoolAction(this, TEXT("IA_GesturePokerFace"));
    IA_GestureTaunt      = MakeBoolAction(this, TEXT("IA_GestureTaunt"));
    IA_GestureSigh       = MakeBoolAction(this, TEXT("IA_GestureSigh"));
    IA_GestureCelebrate  = MakeBoolAction(this, TEXT("IA_GestureCelebrate"));

    // Hardcoded defaults — child classes can rebuild InputMapping to override.
    InputMapping->MapKey(IA_Bet5,             EKeys::One);
    InputMapping->MapKey(IA_Bet25,            EKeys::Two);
    InputMapping->MapKey(IA_Bet100,           EKeys::Three);
    InputMapping->MapKey(IA_Hit,              EKeys::H);
    InputMapping->MapKey(IA_Stand,            EKeys::S);
    InputMapping->MapKey(IA_Double,           EKeys::D);
    InputMapping->MapKey(IA_Split,            EKeys::P);
    InputMapping->MapKey(IA_Surrender,        EKeys::R);
    InputMapping->MapKey(IA_NewRound,         EKeys::N);
    InputMapping->MapKey(IA_GestureConfident, EKeys::C);
    InputMapping->MapKey(IA_GestureNervous,   EKeys::X);
    InputMapping->MapKey(IA_GesturePokerFace, EKeys::O);
    InputMapping->MapKey(IA_GestureTaunt,     EKeys::T);
    InputMapping->MapKey(IA_GestureSigh,      EKeys::G);
    InputMapping->MapKey(IA_GestureCelebrate, EKeys::V);
}

void ABlackjackSamplePlayerController::ActivateInputMapping()
{
    if (!InputMapping) return;
    ULocalPlayer* LP = GetLocalPlayer();
    if (!LP) return;
    if (UEnhancedInputLocalPlayerSubsystem* EISub = LP->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>())
    {
        EISub->ClearAllMappings();
        EISub->AddMappingContext(InputMapping, /*Priority=*/0);
    }
}

// ---------------------------------------------------------------------------
// Action handlers — resolve net-client, send with claimed seat index.
// ---------------------------------------------------------------------------

UBlackjackNetClient* ABlackjackSamplePlayerController::GetNetClient() const
{
    const UGameInstance* GI = GetGameInstance();
    return GI ? GI->GetSubsystem<UBlackjackNetClient>() : nullptr;
}

void ABlackjackSamplePlayerController::PlaceQuickBet(int32 Amount)
{
    if (ClaimedSeatIndex < 0) return;
    if (UBlackjackNetClient* Net = GetNetClient())
    {
        Net->SendPlaceBet(ClaimedSeatIndex, Amount, /*PerfectPairs=*/0, /*TwentyOneP3=*/0, /*LuckyLadies=*/0);
    }
}

void ABlackjackSamplePlayerController::SendGesture(EBlackjackGesture Gesture)
{
    if (ClaimedSeatIndex < 0) return;
    if (UBlackjackNetClient* Net = GetNetClient())
    {
        Net->SendGesture(ClaimedSeatIndex, Gesture);
    }
}

void ABlackjackSamplePlayerController::HandleHit(const FInputActionValue&)
{
    if (ClaimedSeatIndex < 0) return;
    if (UBlackjackNetClient* Net = GetNetClient()) Net->SendHit(ClaimedSeatIndex);
}
void ABlackjackSamplePlayerController::HandleStand(const FInputActionValue&)
{
    if (ClaimedSeatIndex < 0) return;
    if (UBlackjackNetClient* Net = GetNetClient()) Net->SendStand(ClaimedSeatIndex);
}
void ABlackjackSamplePlayerController::HandleDouble(const FInputActionValue&)
{
    if (ClaimedSeatIndex < 0) return;
    if (UBlackjackNetClient* Net = GetNetClient()) Net->SendDouble(ClaimedSeatIndex);
}
void ABlackjackSamplePlayerController::HandleSplit(const FInputActionValue&)
{
    if (ClaimedSeatIndex < 0) return;
    if (UBlackjackNetClient* Net = GetNetClient()) Net->SendSplit(ClaimedSeatIndex);
}
void ABlackjackSamplePlayerController::HandleSurrender(const FInputActionValue&)
{
    if (ClaimedSeatIndex < 0) return;
    if (UBlackjackNetClient* Net = GetNetClient()) Net->SendSurrender(ClaimedSeatIndex);
}
void ABlackjackSamplePlayerController::HandleNewRound(const FInputActionValue&)
{
    if (UBlackjackNetClient* Net = GetNetClient()) Net->SendNewRound();
}

// ---------------------------------------------------------------------------
// Seat bookkeeping — capture our seat index when SEAT_ASSIGNED fires for us.
// The server echoes our session id as OwnerClientId; compare to our net client's
// SessionId to pick only our own assignment out of the multicast.
// ---------------------------------------------------------------------------

void ABlackjackSamplePlayerController::HandleSeatAssigned(int32 SeatIndex, const FString& OwnerClientId)
{
    if (UBlackjackNetClient* Net = GetNetClient())
    {
        if (!OwnerClientId.IsEmpty() && OwnerClientId == Net->GetSessionId())
        {
            ClaimedSeatIndex = SeatIndex;
        }
    }
}

void ABlackjackSamplePlayerController::HandleSeatReleased(int32 SeatIndex, bool /*bBecameNpc*/, const FString& /*Personality*/)
{
    if (SeatIndex == ClaimedSeatIndex)
    {
        ClaimedSeatIndex = -1;
    }
}
