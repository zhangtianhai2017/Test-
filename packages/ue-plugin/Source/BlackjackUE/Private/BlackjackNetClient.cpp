#include "BlackjackNetClient.h"

#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "TimerManager.h"
#include "WebSocketsModule.h"
#include "IWebSocket.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Modules/ModuleManager.h"

DEFINE_LOG_CATEGORY_STATIC(LogBlackjackNet, Log, All);

namespace
{
    const TCHAR* const kClientVersion = TEXT("ue-0.1.0");

    // -----------------------------------------------------------------------
    // M5b.2a — wire-literal -> enum helpers (file-local).
    //
    // These mirror the string enums in packages/game-server/src/protocol/*.
    // All of them fall through to a sane default on unknown input and log at
    // Verbose so we never crash on an unexpected/forward-compatible server.
    // -----------------------------------------------------------------------

    EBlackjackPhase PhaseFromWire(const FString& s)
    {
        if (s == TEXT("betting"))     return EBlackjackPhase::Betting;
        if (s == TEXT("dealing"))     return EBlackjackPhase::Dealing;
        if (s == TEXT("insurance"))   return EBlackjackPhase::Insurance;
        if (s == TEXT("playerTurn"))  return EBlackjackPhase::PlayerTurn;
        if (s == TEXT("dealerTurn"))  return EBlackjackPhase::DealerTurn;
        if (s == TEXT("settlement"))  return EBlackjackPhase::Settlement;
        if (s == TEXT("roundOver"))   return EBlackjackPhase::RoundOver;
        UE_LOG(LogTemp, Verbose, TEXT("Unknown phase: %s"), *s);
        return EBlackjackPhase::Betting;
    }

    EBlackjackAction ActionFromWire(const FString& s)
    {
        if (s == TEXT("hit"))                                          return EBlackjackAction::Hit;
        if (s == TEXT("stand"))                                        return EBlackjackAction::Stand;
        if (s == TEXT("double"))                                       return EBlackjackAction::Double;
        if (s == TEXT("split"))                                        return EBlackjackAction::Split;
        if (s == TEXT("surrender"))                                    return EBlackjackAction::Surrender;
        if (s == TEXT("insure"))                                       return EBlackjackAction::Insure;
        if (s == TEXT("decline-insurance") ||
            s == TEXT("declineInsurance"))                             return EBlackjackAction::DeclineInsurance;
        UE_LOG(LogTemp, Verbose, TEXT("Unknown action: %s"), *s);
        return EBlackjackAction::Stand;
    }

    EBlackjackDealerAction DealerActionFromWire(const FString& s)
    {
        if (s == TEXT("hit"))   return EBlackjackDealerAction::Hit;
        if (s == TEXT("stand")) return EBlackjackDealerAction::Stand;
        if (s == TEXT("bust"))  return EBlackjackDealerAction::Bust;
        UE_LOG(LogTemp, Verbose, TEXT("Unknown dealer action: %s"), *s);
        return EBlackjackDealerAction::Stand;
    }

    EBlackjackOutcome OutcomeFromWire(const FString& s)
    {
        if (s == TEXT("win"))       return EBlackjackOutcome::Win;
        if (s == TEXT("loss"))      return EBlackjackOutcome::Loss;
        if (s == TEXT("push"))      return EBlackjackOutcome::Push;
        if (s == TEXT("blackjack")) return EBlackjackOutcome::Blackjack;
        if (s == TEXT("bust"))      return EBlackjackOutcome::Bust;
        if (s == TEXT("surrender")) return EBlackjackOutcome::Surrender;
        UE_LOG(LogTemp, Verbose, TEXT("Unknown outcome: %s"), *s);
        return EBlackjackOutcome::Loss;
    }

    // Reuses the existing EBlackjackTarget (Player / Dealer) from BlackjackTypes.h
    // for the DEAL_TARGET wire literal.
    EBlackjackTarget DealTargetFromWire(const FString& s)
    {
        if (s == TEXT("dealer")) return EBlackjackTarget::Dealer;
        return EBlackjackTarget::Player; // default
    }

    // Reuses the existing EBlackjackSideBet from BlackjackTypes.h for the
    // side-bet "kind" wire literal.
    EBlackjackSideBet SideBetKindFromWire(const FString& s)
    {
        if (s == TEXT("perfectPairs"))                             return EBlackjackSideBet::PerfectPairs;
        if (s == TEXT("21+3") || s == TEXT("twentyOneP3"))         return EBlackjackSideBet::TwentyOneP3;
        if (s == TEXT("luckyLadies"))                              return EBlackjackSideBet::LuckyLadies;
        UE_LOG(LogTemp, Verbose, TEXT("Unknown sidebet: %s"), *s);
        return EBlackjackSideBet::PerfectPairs;
    }

    EBlackjackRuleSet RuleSetFromWire(const FString& s)
    {
        if (s == TEXT("SPANISH21"))    return EBlackjackRuleSet::Spanish21;
        if (s == TEXT("PONTOON"))      return EBlackjackRuleSet::Pontoon;
        if (s == TEXT("SUPER_FUN_21")) return EBlackjackRuleSet::SuperFun21;
        return EBlackjackRuleSet::Vegas; // default (covers "VEGAS" + unknown)
    }

    EBlackjackLanguage LanguageFromWire(const FString& s)
    {
        if (s == TEXT("en")) return EBlackjackLanguage::English;
        return EBlackjackLanguage::Chinese;
    }

    EBlackjackSeatKind SeatKindFromWire(const FString& s)
    {
        if (s == TEXT("human")) return EBlackjackSeatKind::Human;
        if (s == TEXT("npc"))   return EBlackjackSeatKind::Npc;
        return EBlackjackSeatKind::Empty;
    }

    EBlackjackGesture GestureFromWire(const FString& s)
    {
        if (s == TEXT("nervous"))    return EBlackjackGesture::Nervous;
        if (s == TEXT("poker-face")) return EBlackjackGesture::PokerFace;
        if (s == TEXT("taunt"))      return EBlackjackGesture::Taunt;
        if (s == TEXT("sigh"))       return EBlackjackGesture::Sigh;
        if (s == TEXT("celebrate"))  return EBlackjackGesture::Celebrate;
        return EBlackjackGesture::Confident;
    }

    // -----------------------------------------------------------------------
    // M5b.2b — JSON -> USTRUCT parse helpers (file-local).
    //
    // These mirror the shapes emitted by packages/game-server/src/protocol/
    // toProtocol.ts. Every helper is tolerant of missing fields (Try* does
    // not touch the out parameter on failure, so struct defaults stick) and
    // guards against null `Obj` by returning a default-constructed value.
    //
    // Numeric fields come over the wire as JSON numbers; TryGetNumberField's
    // int32 overload handles the narrowing.
    // -----------------------------------------------------------------------

    FBlackjackCardPayload ParseCardPayload(const TSharedPtr<FJsonObject>& Obj)
    {
        FBlackjackCardPayload Out;
        if (!Obj.IsValid())
        {
            UE_LOG(LogTemp, Verbose, TEXT("ParseCardPayload: null object"));
            return Out;
        }

        bool bFaceDown = false;
        Obj->TryGetBoolField(TEXT("faceDown"), bFaceDown);

        FString Rank;
        FString Suit;
        const bool bHasRank = Obj->TryGetStringField(TEXT("rank"), Rank);
        const bool bHasSuit = Obj->TryGetStringField(TEXT("suit"), Suit);

        if (bFaceDown || !bHasRank || !bHasSuit)
        {
            Out.bFaceDown = true;
            // Leave Rank/Suit empty.
        }
        else
        {
            Out.Rank = Rank;
            Out.Suit = Suit;
            Out.bFaceDown = false;
        }
        return Out;
    }

    FBlackjackHand ParseHand(const TSharedPtr<FJsonObject>& Obj)
    {
        FBlackjackHand Out;
        if (!Obj.IsValid())
        {
            UE_LOG(LogTemp, Verbose, TEXT("ParseHand: null object"));
            return Out;
        }

        const TArray<TSharedPtr<FJsonValue>>* CardsArray = nullptr;
        if (Obj->TryGetArrayField(TEXT("cards"), CardsArray) && CardsArray)
        {
            Out.Cards.Reserve(CardsArray->Num());
            for (const TSharedPtr<FJsonValue>& V : *CardsArray)
            {
                if (V.IsValid())
                {
                    Out.Cards.Add(ParseCardPayload(V->AsObject()));
                }
            }
        }

        Obj->TryGetNumberField(TEXT("bet"), Out.Bet);
        Obj->TryGetBoolField(TEXT("doubled"), Out.bDoubled);
        Obj->TryGetBoolField(TEXT("stood"), Out.bStood);
        Obj->TryGetBoolField(TEXT("surrendered"), Out.bSurrendered);
        // Trust server-computed total / soft / isBust (see toProtocol.ts).
        Obj->TryGetNumberField(TEXT("total"), Out.Total);
        Obj->TryGetBoolField(TEXT("soft"), Out.bSoft);
        Obj->TryGetBoolField(TEXT("isBust"), Out.bIsBust);
        return Out;
    }

    FBlackjackSeatPayload ParseSeat(const TSharedPtr<FJsonObject>& Obj)
    {
        FBlackjackSeatPayload Out;
        if (!Obj.IsValid())
        {
            UE_LOG(LogTemp, Verbose, TEXT("ParseSeat: null object"));
            return Out;
        }

        Obj->TryGetNumberField(TEXT("index"), Out.Index);

        FString KindStr;
        if (Obj->TryGetStringField(TEXT("kind"), KindStr))
        {
            Out.Kind = SeatKindFromWire(KindStr);
        }

        Obj->TryGetStringField(TEXT("name"), Out.Name);
        Obj->TryGetStringField(TEXT("personality"), Out.Personality);
        Obj->TryGetNumberField(TEXT("bankroll"), Out.Bankroll);
        Obj->TryGetStringField(TEXT("ownerSessionId"), Out.OwnerSessionId);
        Obj->TryGetNumberField(TEXT("pendingBet"), Out.PendingBet);
        Obj->TryGetNumberField(TEXT("activeHandIndex"), Out.ActiveHandIndex);

        const TArray<TSharedPtr<FJsonValue>>* HandsArray = nullptr;
        if (Obj->TryGetArrayField(TEXT("hands"), HandsArray) && HandsArray)
        {
            Out.Hands.Reserve(HandsArray->Num());
            for (const TSharedPtr<FJsonValue>& V : *HandsArray)
            {
                if (V.IsValid())
                {
                    Out.Hands.Add(ParseHand(V->AsObject()));
                }
            }
        }

        double TiltD = 0.0;
        if (Obj->TryGetNumberField(TEXT("tilt"), TiltD))
        {
            Out.Tilt = static_cast<float>(TiltD);
        }

        const TArray<TSharedPtr<FJsonValue>>* GesturesArray = nullptr;
        if (Obj->TryGetArrayField(TEXT("gestures"), GesturesArray) && GesturesArray)
        {
            Out.Gestures.Reserve(GesturesArray->Num());
            for (const TSharedPtr<FJsonValue>& V : *GesturesArray)
            {
                if (V.IsValid())
                {
                    Out.Gestures.Add(V->AsString());
                }
            }
        }
        return Out;
    }

    FBlackjackTableHandResult ParseHandResult(const TSharedPtr<FJsonObject>& Obj)
    {
        FBlackjackTableHandResult Out;
        if (!Obj.IsValid())
        {
            UE_LOG(LogTemp, Verbose, TEXT("ParseHandResult: null object"));
            return Out;
        }

        Obj->TryGetNumberField(TEXT("seatIndex"), Out.SeatIndex);
        Obj->TryGetNumberField(TEXT("handIndex"), Out.HandIndex);

        FString OutcomeStr;
        if (Obj->TryGetStringField(TEXT("outcome"), OutcomeStr))
        {
            Out.Outcome = OutcomeFromWire(OutcomeStr);
        }

        Obj->TryGetNumberField(TEXT("payout"), Out.Payout);
        Obj->TryGetNumberField(TEXT("total"), Out.Total);
        Obj->TryGetStringField(TEXT("label"), Out.Label);

        const TArray<TSharedPtr<FJsonValue>>* CardsArray = nullptr;
        if (Obj->TryGetArrayField(TEXT("cards"), CardsArray) && CardsArray)
        {
            Out.Cards.Reserve(CardsArray->Num());
            for (const TSharedPtr<FJsonValue>& V : *CardsArray)
            {
                if (V.IsValid())
                {
                    Out.Cards.Add(ParseCardPayload(V->AsObject()));
                }
            }
        }
        return Out;
    }

    FBlackjackTableSummary ParseTableSummary(const TSharedPtr<FJsonObject>& Obj)
    {
        FBlackjackTableSummary Out;
        if (!Obj.IsValid())
        {
            UE_LOG(LogTemp, Verbose, TEXT("ParseTableSummary: null object"));
            return Out;
        }

        Obj->TryGetStringField(TEXT("tableId"), Out.TableId);

        FString RuleSetStr;
        if (Obj->TryGetStringField(TEXT("ruleSet"), RuleSetStr))
        {
            Out.RuleSet = RuleSetFromWire(RuleSetStr);
        }

        Obj->TryGetNumberField(TEXT("seatsTaken"), Out.SeatsTaken);
        Obj->TryGetNumberField(TEXT("maxSeats"), Out.MaxSeats);
        return Out;
    }

    FBlackjackTableStateSnapshot ParseTableStateSnapshot(const TSharedPtr<FJsonObject>& Obj)
    {
        FBlackjackTableStateSnapshot Out;
        if (!Obj.IsValid())
        {
            UE_LOG(LogTemp, Verbose, TEXT("ParseTableStateSnapshot: null object"));
            return Out;
        }

        Obj->TryGetStringField(TEXT("tableId"), Out.TableId);

        FString PhaseStr;
        if (Obj->TryGetStringField(TEXT("phase"), PhaseStr))
        {
            Out.Phase = PhaseFromWire(PhaseStr);
        }

        FString RuleSetStr;
        if (Obj->TryGetStringField(TEXT("ruleSet"), RuleSetStr))
        {
            Out.RuleSet = RuleSetFromWire(RuleSetStr);
        }

        Obj->TryGetNumberField(TEXT("maxSeats"), Out.MaxSeats);
        Obj->TryGetNumberField(TEXT("activeSeatIndex"), Out.ActiveSeatIndex);

        const TArray<TSharedPtr<FJsonValue>>* DealerArray = nullptr;
        if (Obj->TryGetArrayField(TEXT("dealer"), DealerArray) && DealerArray)
        {
            Out.Dealer.Reserve(DealerArray->Num());
            for (const TSharedPtr<FJsonValue>& V : *DealerArray)
            {
                if (V.IsValid())
                {
                    Out.Dealer.Add(ParseCardPayload(V->AsObject()));
                }
            }
        }

        const TArray<TSharedPtr<FJsonValue>>* SeatsArray = nullptr;
        if (Obj->TryGetArrayField(TEXT("seats"), SeatsArray) && SeatsArray)
        {
            Out.Seats.Reserve(SeatsArray->Num());
            for (const TSharedPtr<FJsonValue>& V : *SeatsArray)
            {
                if (V.IsValid())
                {
                    Out.Seats.Add(ParseSeat(V->AsObject()));
                }
            }
        }

        Obj->TryGetStringField(TEXT("dealerPersona"), Out.DealerPersona);

        FString LangStr;
        if (Obj->TryGetStringField(TEXT("language"), LangStr))
        {
            Out.Language = LanguageFromWire(LangStr);
        }

        const TArray<TSharedPtr<FJsonValue>>* ResultsArray = nullptr;
        if (Obj->TryGetArrayField(TEXT("roundResults"), ResultsArray) && ResultsArray)
        {
            Out.RoundResults.Reserve(ResultsArray->Num());
            for (const TSharedPtr<FJsonValue>& V : *ResultsArray)
            {
                if (V.IsValid())
                {
                    Out.RoundResults.Add(ParseHandResult(V->AsObject()));
                }
            }
        }
        return Out;
    }
}

void UBlackjackNetClient::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);

    // Make sure the WebSockets module is loaded before we try to create sockets.
    // It's safe to call LoadModuleChecked even if the module was already loaded.
    FModuleManager::Get().LoadModuleChecked(TEXT("WebSockets"));

    State = EBlackjackConnectionState::Disconnected;
    SessionId.Reset();
    DisplayName.Reset();
    PendingResumeSessionId.Reset();
    ReconnectGraceSeconds = 0;
}

void UBlackjackNetClient::Deinitialize()
{
    StopPingTimer();
    ReleaseSocket();
    Super::Deinitialize();
}

void UBlackjackNetClient::Connect(const FString& Host, int32 Port, const FString& InDisplayName)
{
    // If we're already connected (or mid-connection), close first so we start clean.
    if (Socket.IsValid())
    {
        Disconnect();
    }

    DisplayName = InDisplayName;

    // If we have a lingering session from a prior connection, try to resume it.
    if (!SessionId.IsEmpty())
    {
        PendingResumeSessionId = SessionId;
    }
    else
    {
        PendingResumeSessionId.Reset();
    }

    const FString Url = FString::Printf(TEXT("ws://%s:%d/game"), *Host, Port);
    UE_LOG(LogBlackjackNet, Log, TEXT("Connecting to %s as '%s'%s"),
        *Url,
        *DisplayName,
        PendingResumeSessionId.IsEmpty() ? TEXT("") : TEXT(" (resume)"));

    Socket = FWebSocketsModule::Get().CreateWebSocket(Url);
    if (!Socket.IsValid())
    {
        UE_LOG(LogBlackjackNet, Error, TEXT("CreateWebSocket returned null for %s"), *Url);
        SetState(EBlackjackConnectionState::Disconnected);
        return;
    }

    Socket->OnConnected().AddUObject(this, &UBlackjackNetClient::HandleConnected);
    Socket->OnConnectionError().AddUObject(this, &UBlackjackNetClient::HandleConnectionError);
    Socket->OnClosed().AddUObject(this, &UBlackjackNetClient::HandleClosed);
    Socket->OnMessage().AddUObject(this, &UBlackjackNetClient::HandleMessage);

    SetState(EBlackjackConnectionState::Connecting);
    Socket->Connect();
}

void UBlackjackNetClient::Disconnect()
{
    StopPingTimer();

    if (Socket.IsValid())
    {
        if (Socket->IsConnected())
        {
            Socket->Close();
        }
    }
    ReleaseSocket();

    // Note: we intentionally keep SessionId around so a follow-up Connect()
    // can resume within the server's grace window (D-022).
    SetState(EBlackjackConnectionState::Disconnected);
}

void UBlackjackNetClient::ReleaseSocket()
{
    if (Socket.IsValid())
    {
        Socket->OnConnected().RemoveAll(this);
        Socket->OnConnectionError().RemoveAll(this);
        Socket->OnClosed().RemoveAll(this);
        Socket->OnMessage().RemoveAll(this);
        Socket.Reset();
    }
}

void UBlackjackNetClient::SetState(EBlackjackConnectionState NewState)
{
    if (State == NewState)
    {
        return;
    }
    State = NewState;
    OnConnectionStateChanged.Broadcast(State);
}

void UBlackjackNetClient::HandleConnected()
{
    UE_LOG(LogBlackjackNet, Log, TEXT("WebSocket connected; sending HELLO."));
    SetState(EBlackjackConnectionState::Awaiting_Hello);
    SendHello();
}

void UBlackjackNetClient::HandleConnectionError(const FString& Error)
{
    UE_LOG(LogBlackjackNet, Warning, TEXT("WebSocket connection error: %s"), *Error);
    StopPingTimer();
    ReleaseSocket();
    SetState(EBlackjackConnectionState::Disconnected);
}

void UBlackjackNetClient::HandleClosed(int32 StatusCode, const FString& Reason, bool bWasClean)
{
    UE_LOG(LogBlackjackNet, Log, TEXT("WebSocket closed: code=%d reason='%s' clean=%s"),
        StatusCode, *Reason, bWasClean ? TEXT("true") : TEXT("false"));

    StopPingTimer();
    ReleaseSocket();

    // If we had a session, the server is holding our seats for `ReconnectGraceSeconds`.
    // Report `Closed` so callers know the session is still recoverable via a new Connect().
    if (!SessionId.IsEmpty())
    {
        SetState(EBlackjackConnectionState::Closed);
    }
    else
    {
        SetState(EBlackjackConnectionState::Disconnected);
    }
}

void UBlackjackNetClient::SendHello()
{
    const TSharedRef<FJsonObject> Obj = MakeShared<FJsonObject>();
    Obj->SetNumberField(TEXT("v"), static_cast<double>(PROTOCOL_VERSION));
    Obj->SetStringField(TEXT("type"), TEXT("HELLO"));
    Obj->SetStringField(TEXT("displayName"), DisplayName);
    Obj->SetStringField(TEXT("clientVersion"), kClientVersion);
    if (!PendingResumeSessionId.IsEmpty())
    {
        Obj->SetStringField(TEXT("resumeSessionId"), PendingResumeSessionId);
    }

    FString Out;
    const TSharedRef<TJsonWriter<TCHAR>> Writer =
        TJsonWriterFactory<TCHAR>::Create(&Out);
    FJsonSerializer::Serialize(Obj, Writer);

    SendFrame(Out);
}

void UBlackjackNetClient::SendPing()
{
    if (State != EBlackjackConnectionState::Connected)
    {
        return;
    }
    if (!Socket.IsValid() || !Socket->IsConnected())
    {
        return;
    }

    const int64 NowMs = FDateTime::UtcNow().ToUnixTimestamp() * 1000
        + static_cast<int64>(FDateTime::UtcNow().GetMillisecond());

    const TSharedRef<FJsonObject> Obj = MakeShared<FJsonObject>();
    Obj->SetNumberField(TEXT("v"), static_cast<double>(PROTOCOL_VERSION));
    Obj->SetStringField(TEXT("type"), TEXT("PING"));
    Obj->SetNumberField(TEXT("timestamp"), static_cast<double>(NowMs));

    FString Out;
    const TSharedRef<TJsonWriter<TCHAR>> Writer =
        TJsonWriterFactory<TCHAR>::Create(&Out);
    FJsonSerializer::Serialize(Obj, Writer);

    SendFrame(Out);
}

void UBlackjackNetClient::StartPingTimer()
{
    StopPingTimer();

    UWorld* World = nullptr;
    if (UGameInstance* GI = GetGameInstance())
    {
        World = GI->GetWorld();
    }
    if (!World)
    {
        UE_LOG(LogBlackjackNet, Warning, TEXT("Cannot start ping timer: no world available."));
        return;
    }

    World->GetTimerManager().SetTimer(
        PingTimerHandle,
        this,
        &UBlackjackNetClient::SendPing,
        PingIntervalSeconds,
        /*bLoop=*/ true);
}

void UBlackjackNetClient::StopPingTimer()
{
    if (!PingTimerHandle.IsValid())
    {
        return;
    }

    UWorld* World = nullptr;
    if (UGameInstance* GI = GetGameInstance())
    {
        World = GI->GetWorld();
    }
    if (World)
    {
        World->GetTimerManager().ClearTimer(PingTimerHandle);
    }
    PingTimerHandle.Invalidate();
}

void UBlackjackNetClient::SendFrame(const FString& JsonStr)
{
    if (!Socket.IsValid() || !Socket->IsConnected())
    {
        UE_LOG(LogBlackjackNet, Warning, TEXT("SendFrame called with no open socket; dropping: %s"), *JsonStr);
        return;
    }
    Socket->Send(JsonStr);
}

void UBlackjackNetClient::HandleMessage(const FString& Message)
{
    TSharedPtr<FJsonObject> Obj;
    const TSharedRef<TJsonReader<TCHAR>> Reader = TJsonReaderFactory<TCHAR>::Create(Message);
    if (!FJsonSerializer::Deserialize(Reader, Obj) || !Obj.IsValid())
    {
        UE_LOG(LogBlackjackNet, Warning, TEXT("Failed to parse incoming frame: %s"), *Message);
        return;
    }

    DispatchFrame(Obj);
}

void UBlackjackNetClient::DispatchFrame(const TSharedPtr<FJsonObject>& Frame)
{
    if (!Frame.IsValid())
    {
        return;
    }

    // Validate protocol version first. We accept only the exact literal.
    double Version = 0.0;
    if (!Frame->TryGetNumberField(TEXT("v"), Version) ||
        static_cast<int32>(Version) != PROTOCOL_VERSION)
    {
        const FString Msg = FString::Printf(
            TEXT("Server frame has unsupported protocol version: %.0f (expected %d)"),
            Version, PROTOCOL_VERSION);
        UE_LOG(LogBlackjackNet, Error, TEXT("%s"), *Msg);
        OnServerError.Broadcast(TEXT("BAD_VERSION"), Msg);
        return;
    }

    FString Type;
    if (!Frame->TryGetStringField(TEXT("type"), Type))
    {
        UE_LOG(LogBlackjackNet, Warning, TEXT("Frame missing 'type' field; ignoring."));
        return;
    }

    if (Type == TEXT("WELCOME"))
    {
        FString NewSessionId;
        Frame->TryGetStringField(TEXT("sessionId"), NewSessionId);

        int32 Grace = 0;
        Frame->TryGetNumberField(TEXT("reconnectGraceSeconds"), Grace);

        SessionId = NewSessionId;
        ReconnectGraceSeconds = Grace;
        PendingResumeSessionId.Reset();

        UE_LOG(LogBlackjackNet, Log, TEXT("WELCOME sessionId=%s grace=%ds"), *SessionId, Grace);

        SetState(EBlackjackConnectionState::Connected);
        OnWelcome.Broadcast(SessionId, Grace);
        StartPingTimer();
        return;
    }

    if (Type == TEXT("PONG"))
    {
        // Keep-alive echo; nothing to do in M5a.
        return;
    }

    if (Type == TEXT("ERROR"))
    {
        FString Code;
        FString Msg;
        Frame->TryGetStringField(TEXT("code"), Code);
        Frame->TryGetStringField(TEXT("message"), Msg);
        UE_LOG(LogBlackjackNet, Warning, TEXT("Server ERROR %s: %s"), *Code, *Msg);
        OnServerError.Broadcast(Code, Msg);
        return;
    }

    // M5b will route: TABLE_STATE, CARD_DEALT, PHASE_CHANGED, SEAT_ASSIGNED,
    // HOLE_CARD_REVEALED, ROUND_OVER, BANKROLL_CHANGED, DEALER_QUIP, etc.
    UE_LOG(LogBlackjackNet, Verbose, TEXT("Frame not handled in M5a: %s"), *Type);
}

// ---------------------------------------------------------------------------
// M5b.1 — client-originated frame senders.
//
// Each sender builds a TSharedPtr<FJsonObject>, serializes it, and routes
// through the existing SendFrame() helper. When not Connected, we log and
// silently drop (callers should consult GetConnectionState() first).
// ---------------------------------------------------------------------------

TSharedRef<FJsonObject> UBlackjackNetClient::MakeBaseFrame(const TCHAR* Type) const
{
    const TSharedRef<FJsonObject> Obj = MakeShared<FJsonObject>();
    Obj->SetNumberField(TEXT("v"), static_cast<double>(PROTOCOL_VERSION));
    Obj->SetStringField(TEXT("type"), Type);
    return Obj;
}

void UBlackjackNetClient::SerializeAndSend(const TSharedRef<FJsonObject>& Obj, const TCHAR* TypeForLog)
{
    if (State != EBlackjackConnectionState::Connected)
    {
        UE_LOG(LogBlackjackNet, Verbose,
            TEXT("Dropping outbound %s frame: connection state is %d (not Connected)."),
            TypeForLog, static_cast<int32>(State));
        return;
    }

    FString Out;
    const TSharedRef<TJsonWriter<TCHAR>> Writer = TJsonWriterFactory<TCHAR>::Create(&Out);
    FJsonSerializer::Serialize(Obj, Writer);
    SendFrame(Out);
}

FString UBlackjackNetClient::RuleSetToWire(EBlackjackRuleSet RuleSet)
{
    switch (RuleSet)
    {
    case EBlackjackRuleSet::Vegas:      return TEXT("VEGAS");
    case EBlackjackRuleSet::Spanish21:  return TEXT("SPANISH21");
    case EBlackjackRuleSet::Pontoon:    return TEXT("PONTOON");
    case EBlackjackRuleSet::SuperFun21: return TEXT("SUPER_FUN_21");
    default:                            return TEXT("VEGAS");
    }
}

FString UBlackjackNetClient::LanguageToWire(EBlackjackLanguage Lang)
{
    switch (Lang)
    {
    case EBlackjackLanguage::Chinese: return TEXT("zh");
    case EBlackjackLanguage::English: return TEXT("en");
    default:                          return TEXT("zh");
    }
}

FString UBlackjackNetClient::GestureToWire(EBlackjackGesture Gesture)
{
    switch (Gesture)
    {
    case EBlackjackGesture::Confident: return TEXT("confident");
    case EBlackjackGesture::Nervous:   return TEXT("nervous");
    case EBlackjackGesture::PokerFace: return TEXT("poker-face");
    case EBlackjackGesture::Taunt:     return TEXT("taunt");
    case EBlackjackGesture::Sigh:      return TEXT("sigh");
    case EBlackjackGesture::Celebrate: return TEXT("celebrate");
    default:                           return TEXT("poker-face");
    }
}

FString UBlackjackNetClient::SeatKindToWire(EBlackjackSeatKind Kind)
{
    switch (Kind)
    {
    case EBlackjackSeatKind::Empty: return TEXT("empty");
    case EBlackjackSeatKind::Human: return TEXT("human");
    case EBlackjackSeatKind::Npc:   return TEXT("npc");
    default:                        return TEXT("empty");
    }
}

// --- Lobby ------------------------------------------------------------------

void UBlackjackNetClient::ListTables()
{
    const TSharedRef<FJsonObject> Obj = MakeBaseFrame(TEXT("LIST_TABLES"));
    SerializeAndSend(Obj, TEXT("LIST_TABLES"));
}

void UBlackjackNetClient::CreateTable(EBlackjackRuleSet RuleSet, int32 MaxSeats, const FString& DealerPersona, EBlackjackLanguage Language)
{
    const TSharedRef<FJsonObject> Obj = MakeBaseFrame(TEXT("CREATE_TABLE"));
    Obj->SetStringField(TEXT("ruleSet"), RuleSetToWire(RuleSet));
    Obj->SetNumberField(TEXT("maxSeats"), static_cast<double>(MaxSeats));
    Obj->SetStringField(TEXT("dealerPersona"), DealerPersona);
    Obj->SetStringField(TEXT("language"), LanguageToWire(Language));
    SerializeAndSend(Obj, TEXT("CREATE_TABLE"));
}

void UBlackjackNetClient::JoinTable(const FString& TableId, const TArray<int32>& SeatRequest)
{
    const TSharedRef<FJsonObject> Obj = MakeBaseFrame(TEXT("JOIN_TABLE"));
    Obj->SetStringField(TEXT("tableId"), TableId);

    // seatRequest is schema-optional but we always include it for the caller's
    // benefit (explicit empty = "no preference").
    TArray<TSharedPtr<FJsonValue>> SeatArray;
    SeatArray.Reserve(SeatRequest.Num());
    for (const int32 Seat : SeatRequest)
    {
        SeatArray.Add(MakeShared<FJsonValueNumber>(static_cast<double>(Seat)));
    }
    Obj->SetArrayField(TEXT("seatRequest"), SeatArray);

    SerializeAndSend(Obj, TEXT("JOIN_TABLE"));
}

void UBlackjackNetClient::LeaveTable()
{
    const TSharedRef<FJsonObject> Obj = MakeBaseFrame(TEXT("LEAVE_TABLE"));
    SerializeAndSend(Obj, TEXT("LEAVE_TABLE"));
}

// --- Seat management --------------------------------------------------------

void UBlackjackNetClient::ConfigureTable(const TArray<FBlackjackSeatConfig>& Seats)
{
    const TSharedRef<FJsonObject> Obj = MakeBaseFrame(TEXT("CONFIGURE_TABLE"));

    TArray<TSharedPtr<FJsonValue>> SeatArray;
    SeatArray.Reserve(Seats.Num());
    for (const FBlackjackSeatConfig& Seat : Seats)
    {
        const TSharedRef<FJsonObject> SeatObj = MakeShared<FJsonObject>();
        SeatObj->SetStringField(TEXT("kind"), SeatKindToWire(Seat.Kind));

        // Omit default / empty optional fields to minimize wire size and to
        // avoid confusing the server with `""` / `0` defaults.
        if (!Seat.Name.IsEmpty())
        {
            SeatObj->SetStringField(TEXT("name"), Seat.Name);
        }
        if (!Seat.Personality.IsEmpty())
        {
            SeatObj->SetStringField(TEXT("personality"), Seat.Personality);
        }
        if (Seat.Bankroll > 0)
        {
            SeatObj->SetNumberField(TEXT("bankroll"), static_cast<double>(Seat.Bankroll));
        }

        SeatArray.Add(MakeShared<FJsonValueObject>(SeatObj));
    }
    Obj->SetArrayField(TEXT("seats"), SeatArray);

    SerializeAndSend(Obj, TEXT("CONFIGURE_TABLE"));
}

void UBlackjackNetClient::ClaimSeat(int32 SeatIndex, const FString& Name, int32 Bankroll)
{
    const TSharedRef<FJsonObject> Obj = MakeBaseFrame(TEXT("CLAIM_SEAT"));
    Obj->SetNumberField(TEXT("seatIndex"), static_cast<double>(SeatIndex));
    Obj->SetStringField(TEXT("name"), Name);
    // `bankroll` is optional in the schema; only emit when the caller
    // explicitly overrides (> 0).
    if (Bankroll > 0)
    {
        Obj->SetNumberField(TEXT("bankroll"), static_cast<double>(Bankroll));
    }
    SerializeAndSend(Obj, TEXT("CLAIM_SEAT"));
}

void UBlackjackNetClient::ReleaseSeat(int32 SeatIndex, bool bBecomeNpc, const FString& Personality)
{
    const TSharedRef<FJsonObject> Obj = MakeBaseFrame(TEXT("RELEASE_SEAT"));
    Obj->SetNumberField(TEXT("seatIndex"), static_cast<double>(SeatIndex));
    if (bBecomeNpc)
    {
        Obj->SetBoolField(TEXT("becomeNpc"), true);
        if (!Personality.IsEmpty())
        {
            Obj->SetStringField(TEXT("personality"), Personality);
        }
    }
    SerializeAndSend(Obj, TEXT("RELEASE_SEAT"));
}

// --- Gameplay ---------------------------------------------------------------

void UBlackjackNetClient::SendPlaceBet(int32 SeatIndex, int32 Amount, int32 PerfectPairs, int32 TwentyOneP3, int32 LuckyLadies)
{
    const TSharedRef<FJsonObject> Obj = MakeBaseFrame(TEXT("PLACE_BET"));
    Obj->SetNumberField(TEXT("seatIndex"), static_cast<double>(SeatIndex));
    Obj->SetNumberField(TEXT("amount"), static_cast<double>(Amount));

    // Only include sideBets if at least one component is set — saves wire
    // bandwidth and keeps the frame minimal for the common no-side-bet path.
    if (PerfectPairs > 0 || TwentyOneP3 > 0 || LuckyLadies > 0)
    {
        const TSharedRef<FJsonObject> Side = MakeShared<FJsonObject>();
        if (PerfectPairs > 0)
        {
            Side->SetNumberField(TEXT("perfectPairs"), static_cast<double>(PerfectPairs));
        }
        if (TwentyOneP3 > 0)
        {
            Side->SetNumberField(TEXT("twentyOneP3"), static_cast<double>(TwentyOneP3));
        }
        if (LuckyLadies > 0)
        {
            Side->SetNumberField(TEXT("luckyLadies"), static_cast<double>(LuckyLadies));
        }
        Obj->SetObjectField(TEXT("sideBets"), Side);
    }

    SerializeAndSend(Obj, TEXT("PLACE_BET"));
}

void UBlackjackNetClient::SendHit(int32 SeatIndex)
{
    const TSharedRef<FJsonObject> Obj = MakeBaseFrame(TEXT("HIT"));
    Obj->SetNumberField(TEXT("seatIndex"), static_cast<double>(SeatIndex));
    SerializeAndSend(Obj, TEXT("HIT"));
}

void UBlackjackNetClient::SendStand(int32 SeatIndex)
{
    const TSharedRef<FJsonObject> Obj = MakeBaseFrame(TEXT("STAND"));
    Obj->SetNumberField(TEXT("seatIndex"), static_cast<double>(SeatIndex));
    SerializeAndSend(Obj, TEXT("STAND"));
}

void UBlackjackNetClient::SendDouble(int32 SeatIndex)
{
    const TSharedRef<FJsonObject> Obj = MakeBaseFrame(TEXT("DOUBLE"));
    Obj->SetNumberField(TEXT("seatIndex"), static_cast<double>(SeatIndex));
    SerializeAndSend(Obj, TEXT("DOUBLE"));
}

void UBlackjackNetClient::SendSplit(int32 SeatIndex)
{
    const TSharedRef<FJsonObject> Obj = MakeBaseFrame(TEXT("SPLIT"));
    Obj->SetNumberField(TEXT("seatIndex"), static_cast<double>(SeatIndex));
    SerializeAndSend(Obj, TEXT("SPLIT"));
}

void UBlackjackNetClient::SendSurrender(int32 SeatIndex)
{
    const TSharedRef<FJsonObject> Obj = MakeBaseFrame(TEXT("SURRENDER"));
    Obj->SetNumberField(TEXT("seatIndex"), static_cast<double>(SeatIndex));
    SerializeAndSend(Obj, TEXT("SURRENDER"));
}

void UBlackjackNetClient::SendInsure(int32 SeatIndex, int32 Amount)
{
    const TSharedRef<FJsonObject> Obj = MakeBaseFrame(TEXT("INSURE"));
    Obj->SetNumberField(TEXT("seatIndex"), static_cast<double>(SeatIndex));
    Obj->SetNumberField(TEXT("amount"), static_cast<double>(Amount));
    SerializeAndSend(Obj, TEXT("INSURE"));
}

void UBlackjackNetClient::SendDeclineInsurance(int32 SeatIndex)
{
    const TSharedRef<FJsonObject> Obj = MakeBaseFrame(TEXT("DECLINE_INSURANCE"));
    Obj->SetNumberField(TEXT("seatIndex"), static_cast<double>(SeatIndex));
    SerializeAndSend(Obj, TEXT("DECLINE_INSURANCE"));
}

void UBlackjackNetClient::SendNewRound()
{
    const TSharedRef<FJsonObject> Obj = MakeBaseFrame(TEXT("NEW_ROUND"));
    SerializeAndSend(Obj, TEXT("NEW_ROUND"));
}

void UBlackjackNetClient::SendGesture(int32 SeatIndex, EBlackjackGesture Gesture)
{
    const TSharedRef<FJsonObject> Obj = MakeBaseFrame(TEXT("GESTURE"));
    Obj->SetNumberField(TEXT("seatIndex"), static_cast<double>(SeatIndex));
    Obj->SetStringField(TEXT("gesture"), GestureToWire(Gesture));
    SerializeAndSend(Obj, TEXT("GESTURE"));
}
