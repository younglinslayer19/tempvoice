import discord
from discord.ext import commands
from discord.ui import Modal, InputText, View, Select, Button
import sqlite3



channel_name = "📩・join to create"

class TempVoice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.conn = sqlite3.connect('voice_channels.db')
        self.cursor = self.conn.cursor()
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS channels
                          (channel_id INTEGER PRIMARY KEY, owner_id INTEGER)''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS bans
                          (channel_id INTEGER, user_id INTEGER,
                           PRIMARY KEY (channel_id, user_id))''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS channel_settings
                    (channel_id INTEGER PRIMARY KEY, name TEXT, user_limit INTEGER)''')
        self.conn.commit()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if after.channel and after.channel.name == channel_name:
            category = after.channel.category
            channel = await after.channel.guild.create_voice_channel(
                name=f"➕・{member.display_name}'s Channel",
                category=category
            )
            
            self.cursor.execute("SELECT name, user_limit FROM channel_settings WHERE channel_id = ?", 
                              (channel.id,))
            settings = self.cursor.fetchone()
            if settings:
                name, user_limit = settings
                await channel.edit(name=name, user_limit=user_limit)

            await member.move_to(channel)
            await channel.set_permissions(member, manage_channels=True)
            
            self.cursor.execute("INSERT INTO channels VALUES (?, ?)", 
                              (channel.id, member.id))
            self.conn.commit()
            
            view = TempVoiceView(self)
            embed = discord.Embed(
                title=f"{member.display_name}",
                description="# Hier kannst du deinen Channel verwalten.",
                color=discord.Color.yellow()
            )
            embed.set_author(name=f"Temp-Voice", icon_url=f"{member.avatar.url}")
            await channel.send(embed=embed, view=view)

        if after.channel:
            self.cursor.execute("SELECT 1 FROM bans WHERE channel_id = ? AND user_id = ?", 
                              (after.channel.id, member.id))
            if self.cursor.fetchone():
                await member.move_to(None)
                return

        if before.channel:
            self.cursor.execute("SELECT owner_id FROM channels WHERE channel_id = ?", 
                              (before.channel.id,))
            result = self.cursor.fetchone()           
            if result and len(before.channel.members) == 0:
                await before.channel.delete()
                self.cursor.execute("DELETE FROM channels WHERE channel_id = ?", 
                                  (before.channel.id,))
                self.cursor.execute("DELETE FROM bans WHERE channel_id = ?", 
                                  (before.channel.id,))
                self.conn.commit()

class TempVoiceView(View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Kick", style=discord.ButtonStyle.danger, emoji="👢")
    async def kick(self, button: Button, interaction: discord.Interaction):
        channel = interaction.user.voice.channel
        view = KickView(self.cog, channel)
        await interaction.response.send_message("Wähle einen User zum Kicken:", 
                                             view=view, ephemeral=True)

    @discord.ui.button(label="Rename", style=discord.ButtonStyle.primary, emoji="📝")
    async def rename(self, button: Button, interaction: discord.Interaction):
        modal = RenameModal(self.cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Set Limit", style=discord.ButtonStyle.secondary, emoji="🔒")
    async def limit(self, button: Button, interaction: discord.Interaction):
        modal = LimitModal(self.cog)
        await interaction.response.send_modal(modal)        

    @discord.ui.button(label="Ban", style=discord.ButtonStyle.danger, emoji="🔨")
    async def ban(self, button: Button, interaction: discord.Interaction):
        modal = BanModal(self.cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Unban", style=discord.ButtonStyle.success, emoji="🔓") 
    async def unban(self, button: Button, interaction: discord.Interaction):
        channel = interaction.user.voice.channel
        view = UnbanView(self.cog, channel)
        await interaction.response.send_message("Wähle einen User zum Entbannen:", 
                                             view=view, ephemeral=True)

class BanModal(Modal):
    def __init__(self, cog):
        super().__init__(title="User bannen")
        self.cog = cog
        self.add_item(InputText(label="User ID"))

    async def callback(self, interaction: discord.Interaction):
        user_id = int(self.children[0].value)
        channel = interaction.user.voice.channel
        member = interaction.guild.get_member(user_id)
        
        if member:
            await channel.set_permissions(member, connect=False)
            if member.voice and member.voice.channel == channel:
                await member.move_to(None)
            
            self.cog.cursor.execute("INSERT INTO bans (channel_id, user_id) VALUES (?, ?)", 
                                  (channel.id, user_id))
            self.cog.conn.commit()
            await interaction.response.send_message(f"{member.mention} wurde gebannt!", 
                                                 ephemeral=True)
        else:
            await interaction.response.send_message("User nicht gefunden!", ephemeral=True)

class UnbanDropdown(Select):
    def __init__(self, cog, channel):
        self.cog = cog
        self.channel = channel
        
        cog.cursor.execute("SELECT user_id FROM bans WHERE channel_id = ?", (channel.id,))
        banned_users = cog.cursor.fetchall()
        
        options = []
        for user_id in banned_users:
            member = channel.guild.get_member(user_id[0])
            if member:
                options.append(discord.SelectOption(
                    label=f"{member.display_name}",
                    value=str(member.id)
                ))
        
        super().__init__(
            placeholder="Wähle einen User zum Entbannen",
            options=options if options else [discord.SelectOption(label="Keine gebannten User", 
                                                               value="none")]
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("Keine User zum Entbannen verfügbar!", 
                                                 ephemeral=True)
            return
        user_id = int(self.values[0])
        member = self.channel.guild.get_member(user_id)
        
        if member:
            await self.channel.set_permissions(member, connect=None)
            self.cog.cursor.execute("DELETE FROM bans WHERE channel_id = ? AND user_id = ?", 
                                  (self.channel.id, user_id))
            self.cog.conn.commit()
            await interaction.response.send_message(f"{member.mention} wurde entbannt!", 
                                                 ephemeral=True)

class UnbanView(View):
    def __init__(self, cog, channel):
        super().__init__()
        self.add_item(UnbanDropdown(cog, channel))
class KickDropdown(Select):
    def __init__(self, cog, channel):
        self.cog = cog
        self.channel = channel
        
        options = []
        for member in channel.members:
            self.cog.cursor.execute("SELECT owner_id FROM channels WHERE channel_id = ?", 
                                  (channel.id,))
            owner_id = self.cog.cursor.fetchone()[0]
            if member.id != owner_id:
                options.append(discord.SelectOption(
                    label=f"{member.display_name}",
                    value=str(member.id)
                ))
        
        super().__init__(
            placeholder="Wähle einen User zum Kicken",
            options=options if options else [discord.SelectOption(label="Keine User zum Kicken", 
                                                               value="none")]
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("Keine User zum Kicken verfügbar!", 
                                                 ephemeral=True)
            return

        user_id = int(self.values[0])
        member = self.channel.guild.get_member(user_id)
        
        if member:
            await member.move_to(None)
            await interaction.response.send_message(f"{member.mention} wurde gekickt!", 
                                                 ephemeral=True)

class KickView(View):
    def __init__(self, cog, channel):
        super().__init__()
        self.add_item(KickDropdown(cog, channel))

class RenameModal(Modal):
    def __init__(self, cog):
        super().__init__(title="Channel umbenennen")
        self.cog = cog
        self.add_item(InputText(label="Neuer Name"))

    async def callback(self, interaction: discord.Interaction):
        new_name = self.children[0].value
        channel = interaction.user.voice.channel
        
        await channel.edit(name=new_name)
        self.cog.cursor.execute("""INSERT OR REPLACE INTO channel_settings 
                               (channel_id, name) VALUES (?, ?)""", 
                               (channel.id, new_name))
        self.cog.conn.commit()
        
        await interaction.response.send_message(f"Channel wurde zu {new_name} umbenannt!", 
                                             ephemeral=True)

class LimitModal(Modal):
    def __init__(self, cog):
        super().__init__(title="User Limit setzen")
        self.cog = cog
        self.add_item(InputText(label="Maximale Anzahl User (The Max is 99!)"))

    async def callback(self, interaction: discord.Interaction):
        try:
            limit = int(self.children[0].value)
            channel = interaction.user.voice.channel
            
            if limit < len(channel.members):
                view = ConfirmKickView(self.cog, channel, limit)
                await interaction.response.send_message(
                    "Es sind mehr User im Channel als das neue Limit erlaubt. " 
                    "Möchtest du überzählige User kicken?",
                    view=view, ephemeral=True)
            else:
                await self._set_limit(channel, limit)
                await interaction.response.send_message(f"Userlimit wurde auf {limit} gesetzt!", 
                                                     ephemeral=True)
            if limit > 99:
                await interaction.response.send_message(f"Userlimit wurde auf {limit} gesetzt!", 
                                                     ephemeral=True)   
        except ValueError:
            await interaction.response.send_message("Bitte gib eine gültige Zahl ein!", 
                                                 ephemeral=True)

    async def _set_limit(self, channel, limit):
        await channel.edit(user_limit=limit)
        self.cog.cursor.execute("""INSERT OR REPLACE INTO channel_settings 
                               (channel_id, user_limit) VALUES (?, ?)""", 
                               (channel.id, limit))
        self.cog.conn.commit()

class ConfirmKickView(View):
    def __init__(self, cog, channel, limit):
        super().__init__()
        self.cog = cog
        self.channel = channel
        self.limit = limit

    @discord.ui.button(label="Ja", style=discord.ButtonStyle.danger)
    async def confirm(self, button: Button, interaction: discord.Interaction):
        self.cog.cursor.execute("SELECT owner_id FROM channels WHERE channel_id = ?", 
                              (self.channel.id,))
        owner_id = self.cog.cursor.fetchone()[0]
        
        members_to_kick = list(self.channel.members)
        members_to_kick = [m for m in members_to_kick if m.id != owner_id]
        members_to_kick = members_to_kick[self.limit-1:]
        
        for member in members_to_kick:
            await member.move_to(None)
        
        await self._set_limit(self.channel, self.limit)
        await interaction.response.send_message("Überzählige User wurden gekickt und " 
                                             f"Limit auf {self.limit} gesetzt!", 
                                             ephemeral=True)

    @discord.ui.button(label="Nein", style=discord.ButtonStyle.secondary)
    async def cancel(self, button: Button, interaction: discord.Interaction):
        await interaction.response.send_message("Vorgang abgebrochen!", ephemeral=True)

    async def _set_limit(self, channel, limit):
        await channel.edit(user_limit=limit)
        self.cog.cursor.execute("""INSERT OR REPLACE INTO channel_settings 
                               (channel_id, user_limit) VALUES (?, ?)""", 
                               (channel.id, limit))
        self.cog.conn.commit()




def setup(bot):
    bot.add_cog(TempVoice(bot))
