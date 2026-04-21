using UnrealBuildTool;

public class BlackjackUE : ModuleRules
{
    public BlackjackUE(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;
        bUseUnity = false;

        PublicDependencyModuleNames.AddRange(new string[] {
            "Core", "CoreUObject", "Engine", "InputCore", "BlackjackCore",
            "WebSockets", "Json", "JsonUtilities"
        });
        PrivateDependencyModuleNames.AddRange(new string[] {
            "Slate", "SlateCore", "UMG"
        });
    }
}
