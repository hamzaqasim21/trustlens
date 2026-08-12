import json
import pandas as pd

# ---- Load InstaFake (JSON files) ----
with open("instafake-dataset-master/data/fake-v1.0/fakeAccountData.json") as f:
    fake_json = json.load(f)
with open("instafake-dataset-master/data/fake-v1.0/realAccountData.json") as f:
    real_json = json.load(f)

instafake_df = pd.DataFrame(fake_json + real_json)

instafake_common = pd.DataFrame({
    "profile_pic": instafake_df["userHasProfilPic"],
    "username_digit_ratio": instafake_df["usernameDigitCount"] / instafake_df["usernameLength"].replace(0, 1),
    "description_length": instafake_df["userBiographyLength"],
    "private": instafake_df["userIsPrivate"],
    "posts_count": instafake_df["userMediaCount"],
    "followers_count": instafake_df["userFollowerCount"],
    "follows_count": instafake_df["userFollowingCount"],
    "fake": instafake_df["isFake"],
    "source_dataset": "instafake",
})

# ---- Load IFSG (CSV files — both train AND test) ----
ifsg_train = pd.read_csv("goyal-dataset/train.csv")
ifsg_test = pd.read_csv("goyal-dataset/test.csv")
ifsg_df = pd.concat([ifsg_train, ifsg_test], ignore_index=True)

ifsg_common = pd.DataFrame({
    "profile_pic": ifsg_df["profile pic"],
    "username_digit_ratio": ifsg_df["nums/length username"],
    "description_length": ifsg_df["description length"],
    "private": ifsg_df["private"],
    "posts_count": ifsg_df["#posts"],
    "followers_count": ifsg_df["#followers"],
    "follows_count": ifsg_df["#follows"],
    "fake": ifsg_df["fake"],
    "source_dataset": "ifsg",
})

# ---- Merge ----
master_df = pd.concat([instafake_common, ifsg_common], ignore_index=True)

print("Master dataset shape:", master_df.shape)
print("\nClass balance:\n", master_df["fake"].value_counts())
print("\nSource balance:\n", master_df["source_dataset"].value_counts())
print("\nAny nulls?\n", master_df.isnull().sum())

master_df.to_csv("master_dataset.csv", index=False)
print("\nSaved to master_dataset.csv")