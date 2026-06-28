import pathlib, urllib.request, concurrent.futures

base_dir = pathlib.Path('tts_test')
hd_dir = base_dir / 'hd'
hd_dir.mkdir(exist_ok=True)

entries = [
    ('English_expressive_narrator', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065902-LMPXpsKZmtDWrrKa.mp3?Expires=1776639543&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=NUXfbfSQr8yRRTEdASEmR0DOLEc%3D'),
    ('English_radiant_girl', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065902-HljElzvCSGmtoMxU.mp3?Expires=1776639543&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=4djq%2FUqIc41qKjA%2BRsD98xrCzCk%3D'),
    ('English_magnetic_voiced_man', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065902-rcqpLkWZcqrFxWyE.mp3?Expires=1776639543&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=4R1%2FoY2c2cOzLT8crYBzxI8ElDo%3D'),
    ('English_compelling_lady1', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065902-XahgSUYhhAQMWGBp.mp3?Expires=1776639543&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=FjsEJt6wlrbNKvyCWzquKrto8ts%3D'),
    ('English_Aussie_Bloke', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065902-zlWpGMibmuwHGuDb.mp3?Expires=1776639543&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=rqzXZ9QkgFo3TA4nAsOIrvm94XE%3D'),
    ('English_captivating_female1', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065902-CTbiJEPvfnPjXXqG.mp3?Expires=1776639544&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=u0GrYwjYO6PF24nWtCEkYpX68Qk%3D'),
    ('English_Upbeat_Woman', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065904-hPSdDFPeecWftqap.mp3?Expires=1776639545&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=nyAAlIZvkdglWYH85Z98LIIxy08%3D'),
    ('English_Trustworth_Man', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065904-ycTuvEQxBvIdrDKG.mp3?Expires=1776639545&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=0p4jgv9%2F8ncOUbHnZKZvzyjePHA%3D'),
    ('English_CalmWoman', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065904-bmzCpDRMpaSSWoQy.mp3?Expires=1776639545&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=8G9Motv26GLEJxETeMkRvcxMCCQ%3D'),
    ('English_UpsetGirl', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065905-zWAaFaDFzXpdfqiL.mp3?Expires=1776639546&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=qDQu507sMYBGB29td3gPwFpRbmc%3D'),
    ('English_Gentle_voiced_man', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065905-oqPpyMJxphYtZfRN.mp3?Expires=1776639546&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=f1oOxPl0NTuZs4CKOnF6MDbdwBE%3D'),
    ('English_Whispering_girl', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065906-mHOvPxzPpVMGMKTx.mp3?Expires=1776639547&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=8uZagO%2BCEyhMgRSJyDFIgCwUbPY%3D'),
    ('English_Diligent_Man', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065907-sbivMmkfnDDpjaOl.mp3?Expires=1776639548&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=6gWPcqoZca8NFX4jbdxN7QavCwc%3D'),
    ('English_Graceful_Lady', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065907-meIitRvwmWnYqDca.mp3?Expires=1776639549&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=snUBIZopGGOCwnlisuqv1MyipT0%3D'),
    ('English_ReservedYoungMan', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065908-XVvowwcbrblndZJx.mp3?Expires=1776639549&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=GVzAsDqhNFd34x3vLY0gFJCNoCI%3D'),
    ('English_PlayfulGirl', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065907-ASFmeDrngUOvSOBv.mp3?Expires=1776639549&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=I3gnYCYxa6SXpXL1uZK3TjvI8Fc%3D'),
    ('English_ManWithDeepVoice', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065908-ERxugsxAMvuiUpMU.mp3?Expires=1776639549&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=5S0dLSE3VQq9PHOYszEm7T%2B0dls%3D'),
    ('English_MaturePartner', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065909-mLGCgcxpUHCtfAWK.mp3?Expires=1776639550&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=KUlzPr9syUs7zR%2FBecrbNk3QCJ0%3D'),
    ('English_FriendlyPerson', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065909-hmlPnxhplVnzTRat.mp3?Expires=1776639551&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=yI6uLSoKl2Pwp8BCGFdX5M26MGc%3D'),
    ('English_MatureBoss', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065910-izvTopTydKrOfqam.mp3?Expires=1776639551&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=52N3Z6vQctvDw0z5qstxLQc8%2BuI%3D'),
    ('English_Debator', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065910-dZpcadUZyluUcWSj.mp3?Expires=1776639551&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=upE9BRl4sYrMXWXcjAJdB7bnXls%3D'),
    ('English_LovelyGirl', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065910-omheCQtwyiIvHYtu.mp3?Expires=1776639551&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=Ia2QZMsCs5Ap7AVyw2ZGQCNhIa4%3D'),
    ('English_Steadymentor', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065911-CrpcXKcZjlSnTDTi.mp3?Expires=1776639553&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=VIy2vIPa%2FbakGbqsp84HkxRf3o0%3D'),
    ('English_Deep_VoicedGentleman', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065911-UBGuiKgLUVXQEtfZ.mp3?Expires=1776639553&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=%2B5WCdWAbdH6EyPKY%2BnXuYCARQ3I%3D'),
    ('English_Wiselady', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065912-GIlgWgktmHLEedjE.mp3?Expires=1776639553&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=vLDOZCnXSp3KxcLUK7l6kYVtrUs%3D'),
    ('English_CaptivatingStoryteller', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065913-rOPCdkiWKxKtRfxb.mp3?Expires=1776639554&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=0w6PI0g94CMDHYQ6f41NMH2gBfE%3D'),
    ('English_DecentYoungMan', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065913-ZtCifWVnCzBElaGu.mp3?Expires=1776639554&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=HSlmlZ1sO6X2j2fi3%2FRrnACXp1Q%3D'),
    ('English_SentimentalLady', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065913-vKlxQXDzqNGGyNqF.mp3?Expires=1776639555&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=bfXLyui2n6i6%2FP8bgkjtTdR%2FcKc%3D'),
    ('English_ImposingManner', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065914-utwwFXPdtKOgygmN.mp3?Expires=1776639555&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=bcHHmmZiNveifGBVoashSkWOWJ8%3D'),
    ('English_SadTeen', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065914-peZYVSjvhSSRzPBc.mp3?Expires=1776639555&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=PCWaBP7g%2FWRpV7YOftt0lMJl%2BP4%3D'),
    ('English_PassionateWarrior', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065915-umPYGPbvpvbBsuwB.mp3?Expires=1776639556&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=yiNyFNfr0yML%2FuJtLqMbeTKVhhE%3D'),
    ('English_WiseScholar', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065915-pDYLrlbaMtGVBjRN.mp3?Expires=1776639556&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=Oo0ZyqiPwyBUFOoxzAQAF%2FJ06Co%3D'),
    ('English_Soft_spokenGirl', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065915-uDEaCbBVGoeVlado.mp3?Expires=1776639557&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=40vSKDgFa3dw%2BL%2Bzy9TcExFkeMI%3D'),
    ('English_SereneWoman', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065916-suelaqekDvpBjFHp.mp3?Expires=1776639557&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=fY0iInjWzkhsHVwm9XCMaNojZH8%3D'),
    ('English_ConfidentWoman', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065916-hlaPllpcradFezap.mp3?Expires=1776639557&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=Y0fseLka3NAU6O94OsFlCTvX%2Bkw%3D'),
    ('English_PatientMan', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065917-fAUDEtnpTioxpEAW.mp3?Expires=1776639558&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=rRs9l5VZukzd%2BN2X0RBXICxBgC8%3D'),
    ('English_Comedian', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065917-tuXWPowPfmRxrSml.mp3?Expires=1776639559&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=3vbX2SIyChNoXs7HPOT5KFc86sM%3D'),
    ('English_BossyLeader', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065917-NIfwNdjalIDDezoS.mp3?Expires=1776639559&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=kJfqNHVcazSIVwckw5X42qr0liQ%3D'),
    ('English_Strong_WilledBoy', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065918-NrkrKEsNTNCxysSc.mp3?Expires=1776639559&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=5kyzFER2ukKT7NrBfGMzb3Lli0c%3D'),
    ('English_StressedLady', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065918-YajNwApdjeEkwLco.mp3?Expires=1776639560&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=0mtZjN18Jkr%2BZLFSaQB8HHtlLJU%3D'),
    ('English_AssertiveQueen', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065918-oIkKUltDxOUCAlWw.mp3?Expires=1776639560&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=7SH4Y4FvNJY9JMmevGnl7dZ7Ko0%3D'),
    ('English_AnimeCharacter', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065919-OudUrCYUIkUXcFuB.mp3?Expires=1776639561&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=4DmGXoznj5mhF8SGhSJtrf6hOkk%3D'),
    ('English_Jovialman', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065920-BfIWKkBQIlTcEibt.mp3?Expires=1776639561&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=DNedt1Xfjl4gjILr631RaH02MBw%3D'),
    ('English_WhimsicalGirl', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065920-sSSsyXqxiDasTFDB.mp3?Expires=1776639561&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=P7Gs3cKte7d%2FkFr4ySzri69uATA%3D'),
    ('English_Kind_heartedGirl', 'https://minimax-algeng-chat-tts-us.oss-us-east-1.aliyuncs.com/audio%2Ftts-20260419065921-eBBydKMgMHPPeELs.mp3?Expires=1776639562&OSSAccessKeyId=LTAI5tCpJNKCf5EkQHSuL9xg&Signature=1psGe7rPBTXb%2BoUnNjF8yi0vZeU%3D'),
]

def download_one(name_url):
    name, url = name_url
    safe_name = name.replace(' ', '_').replace('-', '_')
    path = hd_dir / f'{safe_name}.mp3'
    try:
        urllib.request.urlretrieve(url, path)
        size = path.stat().st_size
        return f'OK|{name}|{size} bytes'
    except Exception as e:
        return f'ERR|{name}|{e}'

with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
    results = list(ex.map(download_one, entries))

ok = [r for r in results if r.startswith('OK')]
err = [r for r in results if not r.startswith('OK')]
print(f'Downloaded {len(ok)}/45')
for r in sorted(ok):
    print(r)
if err:
    print(f'\nERRORS ({len(err)}):')
    for r in err:
        print(r)
