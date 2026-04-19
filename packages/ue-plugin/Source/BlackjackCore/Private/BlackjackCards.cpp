#include "BlackjackCards.h"

namespace Blackjack
{
    const TCHAR* SuitToChar(ESuit S)
    {
        switch (S)
        {
            case ESuit::Spades:   return TEXT("\u2660");
            case ESuit::Hearts:   return TEXT("\u2665");
            case ESuit::Diamonds: return TEXT("\u2666");
            case ESuit::Clubs:    return TEXT("\u2663");
        }
        return TEXT("?");
    }

    const TCHAR* RankToChar(ERank R)
    {
        static const TCHAR* Names[] = { TEXT("A"), TEXT("2"), TEXT("3"), TEXT("4"), TEXT("5"), TEXT("6"), TEXT("7"), TEXT("8"), TEXT("9"), TEXT("10"), TEXT("J"), TEXT("Q"), TEXT("K") };
        return Names[static_cast<uint8>(R)];
    }

    bool IsRed(const FCard& C) { return C.Suit == ESuit::Hearts || C.Suit == ESuit::Diamonds; }

    int32 RankValue(ERank R)
    {
        if (R == ERank::Ace) return 1;
        if (R == ERank::Jack || R == ERank::Queen || R == ERank::King || R == ERank::Ten) return 10;
        return static_cast<int32>(R) + 1; // Two=1→2 ... Nine=8→9
    }

    double FRng::Next()
    {
        // bit-identical to TS mulberry32
        State = (State + 0x6d2b79f5u);
        uint32 T = State;
        T = (T ^ (T >> 15)) * (T | 1u);
        T ^= T + ((T ^ (T >> 7)) * (T | 61u));
        uint32 R = (T ^ (T >> 14));
        return static_cast<double>(R) / 4294967296.0;
    }

    TArray<FCard> BuildDeck(int32 Decks, bool bRemoveTens)
    {
        TArray<FCard> Out;
        Out.Reserve(Decks * 52);
        static const ESuit Suits[] = { ESuit::Spades, ESuit::Hearts, ESuit::Diamonds, ESuit::Clubs };
        for (int32 D = 0; D < Decks; ++D)
        {
            for (ESuit S : Suits)
            {
                for (uint8 R = 0; R < 13; ++R)
                {
                    const ERank Rank = static_cast<ERank>(R);
                    if (bRemoveTens && Rank == ERank::Ten) continue;
                    Out.Add({ Rank, S });
                }
            }
        }
        return Out;
    }

    void FisherYates(TArray<FCard>& Cards, FRng& Rng)
    {
        for (int32 I = Cards.Num() - 1; I > 0; --I)
        {
            const int32 J = FMath::FloorToInt(Rng.Next() * (I + 1));
            Cards.Swap(I, J);
        }
    }

    FShoe::FShoe(FRng& InRng, int32 Decks, double Penetration, bool bRemoveTens)
        : Rng(&InRng), DeckCount(Decks), PenetrationRatio(Penetration), bRemoveTensFromShoe(bRemoveTens)
    {
        Fill();
    }

    void FShoe::Fill()
    {
        Cards = BuildDeck(DeckCount, bRemoveTensFromShoe);
        FisherYates(Cards, *Rng);
        Cut = FMath::FloorToInt(Cards.Num() * PenetrationRatio);
        Drawn = 0;
    }

    FCard FShoe::Draw()
    {
        if (Drawn >= Cards.Num()) Fill();
        return Cards[Drawn++];
    }

    void FShoe::Reshuffle() { Fill(); }
}
